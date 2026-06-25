# -*- coding: utf-8 -*-
"""盘中实时盯盘 + 触发推送(services 层, v2 重构版)。

MR6 PR-C2a: 由 monolith script/intraday_watch.py 忠实迁入(行为等价)。去副作用:
  - 删 monolith 模块级硬编码常量 + _load_email_from_secrets 那坨 global 重赋值; 配置全走 config.SECRETS
  - codex HTTP 抽到 sources.codex.call_codex; 推送抽到 report.notify; 铁律校验走 _intraday_rules
  - 规则文件读 config.STATE_DIR/"watch_rules.json"(与 api C1 同一文件, 绝对路径防 cron workdir 漂移)

遵守 14_intraday_protocol 铁规: 仅 /quote(新浪秒级, 不计 analyze 配额); 盘中不发评分; codex 研判
经 enforce_intraday_rules 输出层硬校验后才附入推送。

用法(供 systemd): python -m vaxstock.services.intraday [--once] [--force]
"""

import argparse
import datetime as dt
import json
import logging
import os
import time
from typing import Optional
from urllib import parse, request

from vaxstock import config
from vaxstock.report.notify import push_email, push_wechat
from vaxstock.services._intraday_rules import enforce_intraday_rules
from vaxstock.sources.codex import call_codex

logger = logging.getLogger(__name__)

# ==================== 配置(全走 config.SECRETS, 无硬编码/无 global 重赋值) ====================
_S = config.SECRETS
API_BASE = _S.get("api_base", "http://127.0.0.1")   # 本机自调, 默认 localhost
POLL_SECONDS = int(_S.get("intraday_poll_seconds", 300))
QUOTE_TIMEOUT = 15

_CODEX_URL = _S.get("codex_url", "http://127.0.0.1:8317/v1/chat/completions")
_CODEX_MODEL = _S.get("codex_model", "codex")
_CODEX_TOKEN = _S.get("codex_token")
_CODEX_ENABLED = _S.get("codex_enabled", True)
_CODEX_TIMEOUT = int(_S.get("codex_timeout", 30))
_PUSHPLUS_TOKEN = _S.get("pushplus_token", "")

WATCH_RULES_FILE = os.environ.get("WATCH_RULES_FILE") or str(config.STATE_DIR / "watch_rules.json")
RULES_PROMPT_FILE = _S.get("intraday_rules_file") or str(config.PROJECT_ROOT / "deploy" / "intraday_rules.md")

_VALID_TYPES = {"price_above", "price_below", "pct_above", "pct_below"}

DEFAULT_RULES = [
    {"code": "002475", "name": "立讯精密", "type": "price_above", "level": 69.0,
     "note": "📈 立讯站上69! 检查量能是否放大(放量才算真突破), 确认则买入3%, 止损66"},
    {"code": "002475", "name": "立讯精密", "type": "price_below", "level": 66.0,
     "note": "🛑 立讯跌破66! 若已持仓→当日无条件止损出局"},
]


def _smtp_conf() -> Optional[dict]:
    """从 config.SECRETS 适配 report.notify.push_email 的 smtp_conf; 未启用/缺凭据返 None。"""
    s = config.SECRETS
    if not (s.get("email_enabled") and s.get("email_user") and s.get("email_authcode") and s.get("email_to")):
        return None
    return {
        "smtp_server": s.get("smtp_server", "smtp.qq.com"),
        "smtp_port": s.get("smtp_port", 465),
        "sender_email": s["email_user"],
        "sender_password": s["email_authcode"],
        "receiver_email": s["email_to"],
    }


# ==================== 规则加载 ====================

def load_rules():
    """从 WATCH_RULES_FILE 读规则; 失败/无效则用 DEFAULT_RULES。"""
    try:
        with open(WATCH_RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
        clean = []
        for i, r in enumerate(rules):
            if not all(k in r for k in ("code", "name", "type", "level", "note")):
                logger.warning(f"[规则{i}] 字段缺失, 跳过: {r}")
                continue
            if r["type"] not in _VALID_TYPES:
                logger.warning(f"[规则{i}] type非法({r['type']}), 跳过")
                continue
            clean.append(r)
        if clean:
            logger.info(f"已从 {WATCH_RULES_FILE} 载入 {len(clean)} 条规则")
            return clean
        logger.warning(f"{WATCH_RULES_FILE} 无有效规则, 用默认规则")
    except FileNotFoundError:
        logger.warning(f"未找到 {WATCH_RULES_FILE}, 用默认规则")
    except Exception as e:
        logger.warning(f"读取 {WATCH_RULES_FILE} 失败({e}), 用默认规则")
    return list(DEFAULT_RULES)


# ==================== 工具 ====================

def now_str():
    return dt.datetime.now().strftime("%H:%M:%S")


def is_trading_time(force=False, now=None):
    """A股交易时段判断(本地时区需 CST)。now 可注入(测试用), 缺省取实时。"""
    if force:
        return True
    n = now or dt.datetime.now()
    if n.weekday() >= 5:  # 周六日
        return False
    t = n.time()
    morning = dt.time(9, 25) <= t <= dt.time(11, 32)
    afternoon = dt.time(13, 0) <= t <= dt.time(15, 2)
    return morning or afternoon


def fetch_quotes(codes):
    """调 /quote 批量拉实时报价。返回 {code: {...}} 或 None。"""
    q = parse.urlencode({"codes": ",".join(codes)})
    url = f"{API_BASE}/quote?{q}"
    try:
        with request.urlopen(url, timeout=QUOTE_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"/quote 请求失败: {e}")
        return None


def fetch_lite(code):
    """命中触发时拉单票盘中快照(/analyze?lite=1): 价量+均线位置, 无评分/无资金。冷缓存给 45s。"""
    url = f"{API_BASE}/analyze/{code}?lite=1"
    try:
        with request.urlopen(url, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"/analyze lite 失败({code}): {e}")
        return None


def _load_rules_prompt():
    """读 codex system prompt(盘中六铁律); 失败兜底极简铁律串(守住底线)。"""
    try:
        with open(RULES_PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ("你是A股盘中盯盘助手。基于实时快照给≤3行盘中研判。"
                "禁止输出评分(0-3.5)、禁止输出买卖价格指令、不臆测资金方向(快照无资金);"
                "结论必须标注'盘中未定论',资金与评分以EOD报告为准。")


def _codex_verdict(snapshot, trigger_note) -> Optional[str]:
    """把盘中快照+触发原因喂 codex, 返回研判文本; 未启用/无 token/失败 -> None。"""
    if not (_CODEX_ENABLED and _CODEX_TOKEN):
        return None
    user_msg = (f"本次触发: {trigger_note}\n"
                f"实时快照(JSON):\n{json.dumps(snapshot, ensure_ascii=False)}")
    return call_codex(_load_rules_prompt(), user_msg,
                      url=_CODEX_URL, model=_CODEX_MODEL, token=_CODEX_TOKEN, timeout=_CODEX_TIMEOUT)


def check_rule(rule, quote):
    """单条规则是否触发。"""
    price = quote.get("price")
    pct = quote.get("change_pct")
    t = rule["type"]
    if t == "price_above":
        return price is not None and price >= rule["level"]
    if t == "price_below":
        return price is not None and price <= rule["level"]
    if t == "pct_above":
        return pct is not None and pct >= rule["level"]
    if t == "pct_below":
        return pct is not None and pct <= rule["level"]
    return False


def notify(rule, quote):
    """触发: 控制台 + 微信 + 邮箱; 命中后拉快照喂 codex 研判, 经铁律校验后附入。"""
    price = quote.get("price")
    pct = quote.get("change_pct")
    amount_yi = (quote.get("amount") or 0) / 1e8
    title = f"[盯盘] {rule['name']} 触发"
    body = (
        f"{rule['note']}\n"
        f"────────────\n"
        f"现价: {price}  涨跌: {(pct or 0):+.2f}%\n"
        f"成交额: {amount_yi:.2f}亿  振幅: {quote.get('amplitude_pct', 0):.2f}%\n"
        f"时间: {quote.get('trade_time', now_str())}  源: {quote.get('source', '?')}\n"
        f"⚠️ 盘中量能为代理值, 评分以EOD报告为准"
    )
    # 命中后: 拉盘中快照 → codex 研判 → 铁律硬校验 → 附入(失败不影响原始告警)
    snap = fetch_lite(rule["code"])
    verdict = _codex_verdict(snap, rule.get("note", "")) if snap else None
    if verdict:
        verdict = enforce_intraday_rules(verdict)  # 输出层硬校验, 不靠 codex 自觉
        body += f"\n────────────\n🤖 codex盘中研判:\n{verdict}"

    logger.info(f"\n{'='*40}\n🚨 {title}\n{body}\n{'='*40}")
    push_wechat(title, body, pushplus_token=_PUSHPLUS_TOKEN)
    push_email(title, body, smtp_conf=_smtp_conf())


# ==================== 主循环 ====================

def run(once=False, force=False):
    rules = load_rules()
    for r in rules:
        r.setdefault("fired", False)
    fired_keys = set()  # 按 (code,type,level) 跨热重载记忆已触发

    def _rule_key(r):
        return (r.get("code"), r.get("type"), r.get("level"))

    codes = sorted(set(r["code"] for r in rules))
    logger.info(f"盯盘启动. 监控 {len(codes)} 只: {codes}")
    chans = []
    if _PUSHPLUS_TOKEN:
        chans.append("微信")
    if _smtp_conf():
        chans.append("邮箱")
    logger.info(f"规则 {len(rules)} 条, 轮询 {POLL_SECONDS}s, "
                f"推送通道: {'+'.join(chans) if chans else '无(仅控制台)'}")

    # 启动自检: 探活
    try:
        with request.urlopen(f"{API_BASE}/health", timeout=10) as r:
            h = json.loads(r.read().decode("utf-8"))
            logger.info(f"/health ok: regime={h.get('regime')} tushare={h.get('tushare_points')}")
    except Exception as e:
        logger.warning(f"服务探活失败: {e} (继续尝试盯盘)")

    while True:
        if not is_trading_time(force):
            n = dt.datetime.now()
            if n.time() > dt.time(15, 2):
                logger.info("收盘, 盯盘结束.")
                break
            logger.info("非交易时段, 等待...")
            if once:
                break
            time.sleep(POLL_SECONDS)
            continue

        # 热重读: 每轮重载规则(API 写接口改了文件即自动生效, 无需重启)
        new_rules = load_rules()
        for r in new_rules:
            r["fired"] = _rule_key(r) in fired_keys  # 保留已触发的静默状态
        rules = new_rules
        codes = sorted(set(r["code"] for r in rules))

        data = fetch_quotes(codes)
        if data:
            line = []
            for c in codes:
                qd = data.get(c, {})
                if qd:
                    line.append(f"{qd.get('name', c)} {qd.get('price')}({qd.get('change_pct', 0):+.1f}%)")
            logger.info(" | ".join(line))

            for rule in rules:
                if rule["fired"]:
                    continue
                qd = data.get(rule["code"])
                if not qd:
                    continue
                if check_rule(rule, qd):
                    notify(rule, qd)
                    rule["fired"] = True
                    fired_keys.add(_rule_key(rule))  # 跨热重载记忆

        if once:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="盘中盯盘 + 触发推送")
    ap.add_argument("--once", action="store_true", help="立即查一次就退出(测试用)")
    ap.add_argument("--force", action="store_true", help="无视交易时段强制轮询(测试用)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    run(once=args.once, force=args.force)
