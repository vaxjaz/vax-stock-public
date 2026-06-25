#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intraday_watch.py — 盘中实时盯盘 + 触发推送
============================================
遵守 14_intraday_protocol.md 铁规:
  - 仅用 /quote (新浪源, 秒级, 不计 analyze 配额)
  - 盘中不计算/不发布 right_side_score 评分
  - 只盯价格/涨跌/振幅/量能等不依赖结算价的字段
设计:
  - 每只票一组触发规则 (进场/止损/异动), 触发一次后该规则静默(避免刷屏)
  - 推送方式可插拔: 控制台始终打印; 填了 PushPlus token 则同时推微信
  - 5 分钟轮询 (可调), 仅在交易时段 09:30-11:30 / 13:00-15:00 运行
策略来源: 2026-06-22 定的立讯 + 券商异动监控
用法:
  python3 intraday_watch.py            # 正常盯盘(交易时段)
  python3 intraday_watch.py --once     # 立即查一次就退出(测试用)
  python3 intraday_watch.py --force    # 无视交易时段, 强制轮询(测试用)
"""

import sys
import time
import json
import datetime as dt
from urllib import request, parse

# ==================== 配置 ====================

API_BASE = "http://vaxjaz.duckdns.org"
POLL_SECONDS = 300          # 轮询间隔(秒), 5分钟
QUOTE_TIMEOUT = 15          # /quote 超时(秒)

# --- 推送配置: 微信和邮箱可同时开/只开一个/都不开(只打印控制台) ---
# 微信: 申请 https://www.pushplus.plus/  登录后拿 token
PUSHPLUS_TOKEN = ""         # ← 填则开微信推送

# 邮箱(QQ): 需在QQ邮箱 设置→账户→开启SMTP服务, 生成"授权码"(非QQ密码)
# 安全建议: 这4项填到 VPS 本地 secrets.json, 别留在脚本里进版本库
EMAIL_ENABLED   = False             # ← 改 True 开启邮箱推送
EMAIL_SMTP      = "smtp.qq.com"
EMAIL_PORT      = 465               # QQ SSL端口
EMAIL_USER      = ""                # ← 发件QQ邮箱, 如 12345@qq.com
EMAIL_AUTHCODE  = ""                # ← QQ邮箱SMTP授权码(16位, 非登录密码)
EMAIL_TO        = ""                # ← 收件邮箱(可与发件相同)

# --- VPS 本机 codex 盘中研判(可选, 命中触发时调用) ---
# ⚠️ 假设 codex 暴露 OpenAI 兼容的 /v1/chat/completions 接口。若你的不是此格式,
#    改 CODEX_URL / 调整 call_codex() 里的 payload 与解析即可。
CODEX_ENABLED     = True
CODEX_URL         = "http://127.0.0.1:8317/v1/chat/completions"
CODEX_MODEL       = "codex"
CODEX_TOKEN       = ""               # ← 从 secrets.json 的 codex_token 读(别硬编码)
CODEX_TIMEOUT     = 30
RULES_PROMPT_FILE = "intraday_rules.md"   # codex system prompt(盘中研判规则)

# 可选: 从 VPS 本地 secrets.json 读 推送+codex 配置(优先于上面硬编码, 更安全)
def _load_email_from_secrets():
    global EMAIL_ENABLED, EMAIL_USER, EMAIL_AUTHCODE, EMAIL_TO, PUSHPLUS_TOKEN
    global CODEX_ENABLED, CODEX_URL, CODEX_MODEL, CODEX_TOKEN
    try:
        with open("secrets.json", encoding="utf-8") as f:
            s = json.load(f)
        if s.get("email_user"):     EMAIL_USER = s["email_user"]
        if s.get("email_authcode"): EMAIL_AUTHCODE = s["email_authcode"]
        if s.get("email_to"):       EMAIL_TO = s["email_to"]
        if s.get("email_enabled"):  EMAIL_ENABLED = bool(s["email_enabled"])
        if s.get("pushplus_token"): PUSHPLUS_TOKEN = s["pushplus_token"]
        if s.get("codex_token"):    CODEX_TOKEN = s["codex_token"]
        if s.get("codex_url"):      CODEX_URL = s["codex_url"]
        if s.get("codex_model"):    CODEX_MODEL = s["codex_model"]
        if "codex_enabled" in s:    CODEX_ENABLED = bool(s["codex_enabled"])
    except Exception:
        pass   # 没有 secrets.json 就用脚本里的硬编码值

# ==================== 监控规则 ====================
# 规则从同目录 watch_rules.json 读取(改规则不用动代码)。
# 文件不存在时用下面的 DEFAULT_RULES 兜底。
#
# JSON 格式(数组, 每条一个规则):
# {
#   "code": "002475", "name": "立讯精密",
#   "type": "price_above",   // price_above/price_below/pct_above/pct_below
#   "level": 69.0,
#   "note": "触发时推送的文案"
# }
#
# type 含义:
#   price_above : 现价 >= level 触发 (进场/突破)
#   price_below : 现价 <= level 触发 (止损/破位)
#   pct_above   : 涨跌幅% >= level 触发 (异动/续强)
#   pct_below   : 涨跌幅% <= level 触发 (跳水)
# 触发后该规则当日静默(fired), 不重复推。重启脚本重置。

RULES_FILE = "watch_rules.json"

DEFAULT_RULES = [
    {"code": "002475", "name": "立讯精密", "type": "price_above", "level": 69.0,
     "note": "📈 立讯站上69! 检查量能是否放大(放量才算真突破), 确认则买入3%, 止损66"},
    {"code": "002475", "name": "立讯精密", "type": "price_below", "level": 66.0,
     "note": "🛑 立讯跌破66! 若已持仓→当日无条件止损出局"},
]

def load_rules():
    """从 watch_rules.json 读规则; 失败则用 DEFAULT_RULES"""
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
        # 基本校验
        valid_types = {"price_above", "price_below", "pct_above", "pct_below"}
        clean = []
        for i, r in enumerate(rules):
            if not all(k in r for k in ("code", "name", "type", "level", "note")):
                print(f"[规则{i}] 字段缺失, 跳过: {r}")
                continue
            if r["type"] not in valid_types:
                print(f"[规则{i}] type非法({r['type']}), 跳过")
                continue
            clean.append(r)
        if clean:
            print(f"已从 {RULES_FILE} 载入 {len(clean)} 条规则")
            return clean
        print(f"⚠️ {RULES_FILE} 无有效规则, 用默认规则")
    except FileNotFoundError:
        print(f"⚠️ 未找到 {RULES_FILE}, 用默认规则(可创建该文件自定义)")
    except Exception as e:
        print(f"⚠️ 读取 {RULES_FILE} 失败({e}), 用默认规则")
    return list(DEFAULT_RULES)

# ==================== 工具函数 ====================

def now_str():
    return dt.datetime.now().strftime("%H:%M:%S")

def is_trading_time(force=False):
    """A股交易时段判断(本地时区需为 CST/Asia-Shanghai)"""
    if force:
        return True
    n = dt.datetime.now()
    if n.weekday() >= 5:          # 周六日
        return False
    t = n.time()
    morning = dt.time(9, 25) <= t <= dt.time(11, 32)
    afternoon = dt.time(13, 0) <= t <= dt.time(15, 2)
    return morning or afternoon

def fetch_quotes(codes):
    """调 /quote 批量拉实时报价. 返回 {code: {字段}} 或 None"""
    q = parse.urlencode({"codes": ",".join(codes)})
    url = f"{API_BASE}/quote?{q}"
    try:
        with request.urlopen(url, timeout=QUOTE_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[{now_str()}] ⚠️ /quote 请求失败: {e}")
        return None

def fetch_lite(code):
    """命中触发时拉单票盘中快照(/analyze?lite=1): 实时价量+均线位置, 无评分/无资金。
    冷缓存首次需串行拉3个Tushare接口(各≤12s超时), 故给45s; 当天缓存热后<3s。"""
    url = f"{API_BASE}/analyze/{code}?lite=1"
    try:
        with request.urlopen(url, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[{now_str()}] ⚠️ /analyze lite 失败({code}): {e}")
        return None

def _load_rules_prompt():
    try:
        with open(RULES_PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    except Exception:
        # 兜底极简规则, 保证即便规则文件丢失也守住铁律
        return ("你是A股盘中盯盘助手。基于实时快照给≤3行盘中研判。"
                "禁止输出评分(0-3.5)、禁止输出买卖价格指令、不臆测资金方向(快照无资金);"
                "结论必须标注'盘中未定论',资金与评分以EOD报告为准。")

def call_codex(snapshot, trigger_note):
    """把盘中快照+触发原因喂 VPS 本机 codex, 返回研判文本. 失败返回 None(不影响告警)。
    默认按 OpenAI 兼容 /v1/chat/completions 调用; 你的 codex 若非此格式, 改这里。"""
    if not (CODEX_ENABLED and CODEX_TOKEN):
        return None
    user_msg = (f"本次触发: {trigger_note}\n"
                f"实时快照(JSON):\n{json.dumps(snapshot, ensure_ascii=False)}")
    payload = json.dumps({
        "model": CODEX_MODEL,
        "messages": [
            {"role": "system", "content": _load_rules_prompt()},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "stream": False,
    }).encode("utf-8")
    req = request.Request(CODEX_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CODEX_TOKEN}",
    })
    try:
        with request.urlopen(req, timeout=CODEX_TIMEOUT) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[{now_str()}] ⚠️ codex 研判失败: {e}")
        return None

def push_wechat(title, content):
    """PushPlus 微信推送. 未配 token 则跳过"""
    if not PUSHPLUS_TOKEN:
        return
    try:
        payload = json.dumps({
            "token": PUSHPLUS_TOKEN,
            "title": title,
            "content": content,
            "template": "txt",
        }).encode("utf-8")
        req = request.Request("https://www.pushplus.plus/send", data=payload,
                              headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode("utf-8"))
            if resp.get("code") != 200:
                print(f"[{now_str()}] ⚠️ 推送返回异常: {resp.get('msg')}")
    except Exception as e:
        print(f"[{now_str()}] ⚠️ 微信推送失败: {e}")

def push_email(title, content):
    """QQ邮箱 SMTP 推送. 未开启则跳过"""
    if not (EMAIL_ENABLED and EMAIL_USER and EMAIL_AUTHCODE and EMAIL_TO):
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    try:
        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO
        msg["Subject"] = Header(title, "utf-8")
        srv = smtplib.SMTP_SSL(EMAIL_SMTP, EMAIL_PORT, timeout=12)
        srv.login(EMAIL_USER, EMAIL_AUTHCODE)
        srv.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        srv.quit()
    except Exception as e:
        print(f"[{now_str()}] ⚠️ 邮件推送失败: {e}")

def notify(rule, quote):
    """触发: 控制台打印 + 微信 + 邮箱; 命中后调 codex 盘中研判并附入"""
    price = quote.get("price")
    pct = quote.get("change_pct")
    amount_yi = (quote.get("amount") or 0) / 1e8
    title = f"[盯盘] {rule['name']} 触发"
    body = (
        f"{rule['note']}\n"
        f"────────────\n"
        f"现价: {price}  涨跌: {pct:+.2f}%\n"
        f"成交额: {amount_yi:.2f}亿  振幅: {quote.get('amplitude_pct', 0):.2f}%\n"
        f"时间: {quote.get('trade_time', now_str())}  源: {quote.get('source','?')}\n"
        f"⚠️ 盘中量能为代理值, 评分以EOD报告为准"
    )
    # 命中后: 拉盘中快照 → 喂 codex 研判(失败不影响原始告警)
    snap = fetch_lite(rule["code"])
    verdict = call_codex(snap, rule.get("note", "")) if snap else None
    if verdict:
        body += f"\n────────────\n🤖 codex盘中研判:\n{verdict}"

    print(f"\n{'='*40}\n🚨 {title}\n{body}\n{'='*40}\n")
    push_wechat(title, body)
    push_email(title, body)

def check_rule(rule, quote):
    """判断单条规则是否触发. 返回 True/False"""
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

# ==================== 主循环 ====================

def run(once=False, force=False):
    _load_email_from_secrets()   # 优先从 VPS secrets.json 读推送配置

    rules = load_rules()         # 从 watch_rules.json 载入监控规则
    for r in rules:
        r.setdefault("fired", False)
    # fired 状态按 code+type+level 记忆, 热重载时保留已触发标记
    fired_keys = set()

    def _rule_key(r):
        return (r.get("code"), r.get("type"), r.get("level"))

    codes = sorted(set(r["code"] for r in rules))
    print(f"[{now_str()}] 盯盘启动. 监控 {len(codes)} 只: {codes}")
    chans = []
    if PUSHPLUS_TOKEN: chans.append("微信")
    if EMAIL_ENABLED and EMAIL_USER and EMAIL_AUTHCODE and EMAIL_TO: chans.append("邮箱")
    print(f"[{now_str()}] 规则 {len(rules)} 条, 轮询 {POLL_SECONDS}s, "
          f"推送通道: {'+'.join(chans) if chans else '无(仅控制台)'}")

    # 启动自检: 探活
    try:
        with request.urlopen(f"{API_BASE}/health", timeout=10) as r:
            h = json.loads(r.read().decode("utf-8"))
            print(f"[{now_str()}] /health ok: regime={h.get('regime')} "
                  f"tushare={h.get('tushare_points')}")
    except Exception as e:
        print(f"[{now_str()}] ⚠️ 服务探活失败: {e} (继续尝试盯盘)")

    while True:
        if not is_trading_time(force):
            n = dt.datetime.now()
            if n.time() > dt.time(15, 2):
                print(f"[{now_str()}] 收盘, 盯盘结束.")
                break
            print(f"[{now_str()}] 非交易时段, 等待...")
            if once:
                break
            time.sleep(POLL_SECONDS)
            continue

        # 热重读: 每轮重新载入规则文件(API写接口改了文件即自动生效, 无需重启)
        new_rules = load_rules()
        for r in new_rules:
            r["fired"] = _rule_key(r) in fired_keys   # 保留已触发的静默状态
        rules = new_rules
        codes = sorted(set(r["code"] for r in rules))

        data = fetch_quotes(codes)
        if data:
            line = []
            for c in codes:
                qd = data.get(c, {})
                if qd:
                    line.append(f"{qd.get('name',c)} {qd.get('price')}({qd.get('change_pct',0):+.1f}%)")
            print(f"[{now_str()}] " + " | ".join(line))

            for rule in rules:
                if rule["fired"]:
                    continue
                qd = data.get(rule["code"])
                if not qd:
                    continue
                if check_rule(rule, qd):
                    notify(rule, qd)
                    rule["fired"] = True
                    fired_keys.add(_rule_key(rule))   # 跨热重载记忆已触发

        if once:
            break
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    run(once="--once" in sys.argv, force="--force" in sys.argv)