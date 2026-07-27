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
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse, request

from vaxstock import config
from vaxstock.report.notify import push_email, push_wechat
from vaxstock.services._intraday_rules import enforce_intraday_rules
from vaxstock.services._t1_baseline import load_t1_baseline
from vaxstock.report.stock_evidence import format_earnings, format_live_history, format_today_strategy
from vaxstock.services.forecast_recorder import load_dline_trigger_facts, record_forecast
from vaxstock.services.observation_coverage import (
    finalize_observation_coverage, record_task_observation,
)
from vaxstock.services.forecast_evolution import (
    finalize_evolutions, record_evolution_observation,
    restore_active_evolutions, start_trigger_evolution,
)
from vaxstock.services.market_health import (
    render_market_health_notification, run_market_health_check,
)
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
DLINE_TASKS_FILE = os.environ.get("DLINE_TASKS_FILE") or str(config.STATE_DIR / "forecast" / "current_tasks.json")
RULES_PROMPT_FILE = _S.get("intraday_rules_file") or str(config.PROJECT_ROOT / "deploy" / "intraday_rules.md")

_VALID_TYPES = {"price_above", "price_below", "pct_above", "pct_below"}

# watchlist 概念标签惰性缓存(进程级, 本 PR 不热重载): None=未加载, {}=加载失败/空池(不臆造)
_concepts_map = None

DEFAULT_RULES = []


def _env_truthy(value: Optional[str], default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _maybe_autocommit_intraday_forecast():
    """Commit/push intraday forecast rows after a live trigger.

    EOD and D-line planning are oneshot services and can use systemd
    ExecStartPost. Intraday is long-running, so forecast rows written during
    the session need an explicit hook here. Failures are logged and never block
    alert delivery.
    """
    if not _env_truthy(os.getenv("GIT_AUTOCOMMIT_INTRADAY"), default=True):
        logger.info("intraday git autocommit disabled by GIT_AUTOCOMMIT_INTRADAY")
        return None
    try:
        from vaxstock.services.git_autocommit import run_autocommit

        result = run_autocommit("intraday")
        logger.info("intraday git autocommit done: %s", result)
        return result
    except Exception as exc:
        logger.warning("intraday git autocommit failed: %s: %s", type(exc).__name__, exc)
        return None


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

def load_rules(holding_codes=None):
    """Load optional legacy watch rules.

    Missing or invalid watch_rules.json returns an empty list.  D-line tasks are
    loaded separately from current_tasks.json; legacy rules must never fall back
    to hard-coded buy/sell instructions.  Production consumption is holdings
    only even if a stale file still contains rules for a sold stock.
    """
    allowed_codes = set(config.load_holdings()) if holding_codes is None else set(holding_codes)
    try:
        with open(WATCH_RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
    except FileNotFoundError:
        logger.info("legacy watch rules missing: %s; disabled", WATCH_RULES_FILE)
        return []
    except Exception as e:
        logger.warning("legacy watch rules invalid: %s; disabled: %s", WATCH_RULES_FILE, e)
        return []

    if not isinstance(rules, list):
        logger.warning("legacy watch rules must be a list: %s; disabled", WATCH_RULES_FILE)
        return []

    clean = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not all(k in r for k in ("code", "name", "type", "level", "note")):
            logger.warning("legacy rule[%s] missing fields, skipped: %s", i, r)
            continue
        if r["type"] not in _VALID_TYPES:
            logger.warning("legacy rule[%s] invalid type=%s, skipped", i, r.get("type"))
            continue
        if str(r.get("code") or "") not in allowed_codes:
            logger.info("legacy rule[%s] is not a current holding, skipped: %s", i, r.get("code"))
            continue
        clean.append(r)
    if clean:
        logger.info("legacy watch rules loaded: %s from %s", len(clean), WATCH_RULES_FILE)
    else:
        logger.info("legacy watch rules empty: %s; disabled", WATCH_RULES_FILE)
    return clean

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


def fetch_market_ctx() -> dict:
    """拉大盘背景(走 api /market 缓存, 单一真相源): regime(新浪指数实时) + overview(涨跌家数, T日收盘聚合)。

    方案A: intraday 只做消费者, 绝不自取 Tushare/全市场(不烧配额, 不重复算)。
    失败 -> 降级 {"regime": None, "overview": {}}(P0: 缺数据不臆造, 由 _codex_verdict 标"待获取")。
    """
    url = f"{API_BASE}/market"
    try:
        with request.urlopen(url, timeout=QUOTE_TIMEOUT) as r:
            j = json.loads(r.read().decode("utf-8"))
        return {"regime": j.get("regime"), "overview": j.get("overview", {})}
    except Exception as e:
        logger.warning(f"/market 请求失败, 大盘背景降级为待获取: {e}")
        return {"regime": None, "overview": {}}


def _get_concepts(code) -> list:
    """Return configured concept tags for watchlist or holding symbols.

    Loaded lazily and cached per process. Missing/invalid config returns [] instead
    of inventing neutral tags. Holdings concepts take precedence because current
    holdings may be intentionally excluded from the observation watchlist.
    """
    global _concepts_map
    if _concepts_map is None:
        try:
            _, loaded = config.load_watchlist()
            _concepts_map = dict(loaded or {})
            for h_code, info in (config.load_holdings() or {}).items():
                if (info or {}).get("concepts"):
                    _concepts_map[h_code] = list(info["concepts"])
        except Exception as e:
            logger.warning(f"concept tags loading failed, this process will use empty tags: {e}")
            _concepts_map = {}
    return _concepts_map.get(code, [])

def _load_rules_prompt():
    """读 codex system prompt(盘中六铁律); 失败兜底极简铁律串(守住底线)。"""
    try:
        with open(RULES_PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ("你是A股盘中盯盘助手。基于实时快照给≤3行盘中研判。"
                "禁止输出评分(0-3.5)、禁止输出买卖价格指令、不臆测资金方向(快照无资金);"
                "结论必须标注'盘中未定论',资金与评分以EOD报告为准。")


# 本策略一行逻辑(硬编码, 喂 codex 做假设检验的"策略锚")
_STRATEGY_LINE = "【本策略逻辑】价值+成长+左侧, 不追高; 右侧评分=资金/业绩/户数三因子, ≥2.0可介入"


def _codex_verdict(snapshot, trigger_note, *, market_ctx=None, concepts=None,
                   fire_count=None, t1_baseline=None) -> Optional[str]:
    """喂 codex 做"今日行为 vs 昨日 thesis"假设检验, 返回 codex 原始 JSON 文本; 未启用/无 token/失败 -> None。

    注入: ① T-1 EOD 基准(昨日定稿, 可引用) ② 本策略逻辑 ③ 大盘背景 ④ lite 实时快照。
    【口径铁律 · P0 数据诚实】
      - regime 走新浪指数实时算(可信), 缺失写"待获取", 绝不臆造;
      - 涨跌家数来自 Tushare 全市场 T日收盘聚合(盘中滞后), 行内必须标注;
      - 快照为 lite(无评分/无资金), 盘中不得新生成评分/买卖价/资金方向; T-1 基准是昨日定稿, 可引用。
    """
    if not (_CODEX_ENABLED and _CODEX_TOKEN):
        return None
    market_ctx = market_ctx or {}
    regime = market_ctx.get("regime")
    ov = market_ctx.get("overview") or {}
    breadth = (f"涨{ov.get('up_count', '?')}/跌{ov.get('down_count', '?')}/"
               f"涨停{ov.get('limit_up_count', '?')}/跌停{ov.get('limit_down_count', '?')}"
               if ov else "待获取")
    concepts_str = "、".join(concepts) if concepts else "无标注"
    nth = fire_count if fire_count else 1
    if t1_baseline:
        b = t1_baseline
        t1_line = (f"【昨日EOD基准(T-1定稿, 可引用)】评分{b.get('score')}[{b.get('grade')}]/"
                   f"10日资金{b.get('main_inflow_10d')}/20日位置{b.get('position_20d_pct')}%/"
                   f"基准日={b.get('baseline_date')}")
    else:
        t1_line = "【无T-1基准】此票不在观察池或昨日无定稿结论"
    user_msg = (
        f"【本次触发】{trigger_note}\n"
        f"{t1_line}\n"
        f"{_STRATEGY_LINE}\n"
        f"【大盘背景】\n"
        f"  实时regime: {regime or '待获取'}(新浪指数实时算)\n"
        f"  涨跌家数(T日收盘聚合, 盘中滞后): {breadth}\n"
        f"【标的】{snapshot.get('code', '?')}  概念: {concepts_str}  今日第{nth}次触发\n"
        f"【实时快照(JSON, lite: 无评分/无资金)】\n{json.dumps(snapshot, ensure_ascii=False)}"
    )
    return call_codex(_load_rules_prompt(), user_msg,
                      url=_CODEX_URL, model=_CODEX_MODEL, token=_CODEX_TOKEN, timeout=_CODEX_TIMEOUT)


def _parse_codex_json(raw) -> Optional[dict]:
    """把 codex 返回文本解析为预测 JSON; 失败返 None(容错: 上层降级纯价位告警, 不崩)。

    宽容处理 codex 可能的 markdown 围栏: 去 ``` 包裹, 截取首个 { 到末个 }。
    """
    if not raw or not isinstance(raw, str):
        return None
    txt = raw.strip()
    i, j = txt.find("{"), txt.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        obj = json.loads(txt[i:j + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


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


# ==================== D-line task execution ====================

def _today_trade_date() -> str:
    """Calendar-day target used only to select already materialized D-line tasks."""
    return dt.date.today().strftime("%Y%m%d")


def _as_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v, digits=2):
    n = _as_float(v)
    if n is None:
        return "待获取"
    return f"{n:.{digits}f}"


def _short(v, limit=160):
    s = str(v or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def load_dline_tasks(target_trade_date: Optional[str] = None, holding_codes=None) -> List[Dict[str, Any]]:
    """Load today's D-line observation tasks from current_tasks.json.

    Missing file means no D-line alerts.  It must never fall back to legacy
    hard-coded watch rules.  A stale task snapshot is intersected with the
    current private holdings at consumption time.
    """
    target = str(target_trade_date or _today_trade_date()).strip()
    allowed_codes = set(config.load_holdings()) if holding_codes is None else set(holding_codes)
    try:
        with open(DLINE_TASKS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.info("D-line task file missing: %s; no D-line alerts", DLINE_TASKS_FILE)
        return []
    except Exception as e:
        logger.warning("D-line task file invalid: %s; no D-line alerts: %s", DLINE_TASKS_FILE, e)
        return []

    rows = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        logger.warning("D-line task file has no task list: %s", DLINE_TASKS_FILE)
        return []

    tasks = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("code") or "") not in allowed_codes:
            continue
        if str(row.get("target_trade_date") or "").strip() != target:
            continue
        obs = row.get("observation") or {}
        blueprints = obs.get("trigger_blueprints") or []
        if not isinstance(blueprints, list) or not blueprints:
            continue
        tasks.append(row)
    if tasks:
        logger.info("D-line tasks loaded: target=%s count=%s source=%s", target, len(tasks), DLINE_TASKS_FILE)
    return tasks


def _quote_feature_values(task: Dict[str, Any], quote: Dict[str, Any]) -> Dict[str, Any]:
    """Merge baseline EOD metrics with live quote fields for D-line DSL checks.

    Price-related moving-average deviations are recomputed from the live quote
    and the frozen EOD MA values.  Non-recomputable fields stay as frozen EOD
    context and are preserved for traceability.
    """
    evidence = task.get("evidence_pack") or {}
    a_eod = evidence.get("A_eod") or {}
    metrics = dict(a_eod.get("metrics") or {})
    values: Dict[str, Any] = {}
    values.update(metrics)

    price = _as_float((quote or {}).get("price"))
    if price is not None:
        values["price"] = price
    change_pct = _as_float((quote or {}).get("change_pct"))
    if change_pct is not None:
        values["change_pct"] = change_pct
    amplitude_pct = _as_float((quote or {}).get("amplitude_pct"))
    if amplitude_pct is not None:
        values["amplitude_pct"] = amplitude_pct
    amount = _as_float((quote or {}).get("amount"))
    if amount is not None:
        values["amount_yi"] = amount / 1e8

    if price is not None:
        for ma_key in ("ma5", "ma10", "ma20", "ma60"):
            ma = _as_float(metrics.get(ma_key))
            if ma and ma != 0:
                field = f"price_vs_{ma_key}_pct"
                values[field] = round((price - ma) / ma * 100, 4)
    return values


def _condition_atom_matches(atom: Dict[str, Any], values: Dict[str, Any]) -> bool:
    field = str(atom.get("field") or "").strip()
    op = str(atom.get("op") or "").strip()
    expected = atom.get("value")
    if not field or op not in {"<", "<=", ">", ">=", "==", "!="}:
        return False
    if field not in values:
        return False
    actual = values.get(field)
    if op in {"==", "!="}:
        ok = str(actual) == str(expected)
        return ok if op == "==" else not ok
    actual_n = _as_float(actual)
    expected_n = _as_float(expected)
    if actual_n is None or expected_n is None:
        return False
    if op == "<":
        return actual_n < expected_n
    if op == "<=":
        return actual_n <= expected_n
    if op == ">":
        return actual_n > expected_n
    if op == ">=":
        return actual_n >= expected_n
    return False


def _condition_matches(condition: Dict[str, Any], values: Dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        return False
    all_atoms = condition.get("all") or []
    any_atoms = condition.get("any") or []
    if not isinstance(all_atoms, list) or not isinstance(any_atoms, list):
        return False
    all_ok = all(_condition_atom_matches(a, values) for a in all_atoms) if all_atoms else True
    any_ok = any(_condition_atom_matches(a, values) for a in any_atoms) if any_atoms else True
    return all_ok and any_ok


def matching_dline_triggers(task: Dict[str, Any], quote: Dict[str, Any]):
    values = _quote_feature_values(task, quote)
    blueprints = ((task.get("observation") or {}).get("trigger_blueprints") or [])
    matches = []
    for idx, bp in enumerate(blueprints):
        if not isinstance(bp, dict):
            continue
        if _condition_matches(bp.get("condition") or {}, values):
            matches.append((idx, bp, values))
    return matches


def check_dline_task(task: Dict[str, Any], quote: Dict[str, Any]) -> Tuple[Optional[int], Optional[Dict[str, Any]], Dict[str, Any]]:
    matches = matching_dline_triggers(task, quote)
    if matches:
        return matches[0]
    values = _quote_feature_values(task, quote)
    return None, None, values


def _dline_reasoning(task: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
    obs = task.get("observation") or {}
    parts = [
        f"D线触发: {_short(blueprint.get('why'), 180)}",
        f"观察目的: {_short(obs.get('observe_intent'), 180)}",
        f"主要风险: {_short(obs.get('primary_risk'), 180)}",
        f"对C线反馈: {_short(blueprint.get('expected_feedback_to_c') or obs.get('c_line_feedback_focus'), 180)}",
        "这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。",
    ]
    return enforce_intraday_rules("\n".join(p for p in parts if p.strip()))


def _fmt_pct_text(v, digits=2, signed=True):
    n = _as_float(v)
    if n is None:
        return "待获取"
    sign = "+" if signed and n > 0 else ""
    return f"{sign}{n:.{digits}f}%"


def _fmt_confidence(v):
    n = _as_float(v)
    if n is None:
        return "待获取"
    if abs(n) <= 1:
        n *= 100
    return f"{n:.0f}%"


def _fmt_amount_yi(values: Dict[str, Any], quote: Dict[str, Any]) -> str:
    amount_yi = _as_float((values or {}).get("amount_yi"))
    if amount_yi is None:
        amount = _as_float((quote or {}).get("amount"))
        amount_yi = None if amount is None else amount / 1e8
    return "待获取" if amount_yi is None else f"{amount_yi:.2f}亿"


def _format_dline_alert_body(code: str, name: str, task: Dict[str, Any], quote: Dict[str, Any],
                             blueprint: Dict[str, Any], values: Dict[str, Any], c_pred: Dict[str, Any],
                             reasoning: str, trigger_type: str, severity: str, fire_count=None,
                             strategy_row=None) -> str:
    values = values or {}
    quote = quote or {}
    expected_feedback = blueprint.get("expected_feedback_to_c") or (task.get("observation") or {}).get("c_line_feedback_focus")
    c_reason = _short(c_pred.get("reason"), 220) or "待获取"
    evidence = task.get("evidence_pack") or {}
    history = evidence.get("B_prediction_history_summary") or {}
    earnings = ((evidence.get("E_context") or {}).get("earnings") or {})
    decision_context = task.get("decision_context") or {}
    lines = [
        f"{code} {name} | {trigger_type} | severity={severity}",
        "",
        "【真实历史结果】",
        format_live_history(history),
        "",
        "【公司财报】",
        format_earnings(earnings),
        "",
        "【今日策略】",
        format_today_strategy(strategy_row or {}),
        "",
        "【触发摘要】",
        f"- 触发依据: {_short(blueprint.get('why'), 260) or '待获取'}",
        f"- 任务: baseline={task.get('baseline_trade_date') or '待获取'} target={task.get('target_trade_date') or '待获取'} task_id={task.get('task_id') or '待获取'} fire_count={fire_count or '待获取'}",
        "",
        "【实时行情】",
        f"- 现价: {_fmt(quote.get('price'))}  涨跌幅: {_fmt_pct_text(quote.get('change_pct'))}  振幅: {_fmt_pct_text(quote.get('amplitude_pct'), signed=False)}  成交额: {_fmt_amount_yi(values, quote)}",
        f"- MA偏离: MA5 {_fmt_pct_text(values.get('price_vs_ma5_pct'))}  MA20 {_fmt_pct_text(values.get('price_vs_ma20_pct'))}  MA60 {_fmt_pct_text(values.get('price_vs_ma60_pct'))}",
        f"- 量能/指标: 5日量比 {_fmt(values.get('volume_ratio_5d'))}  RSI14 {_fmt(values.get('rsi_14'))}  MACD柱 {_fmt(values.get('macd_hist'), 4)}",
        f"- 时间: {quote.get('trade_time', now_str())}  源: {quote.get('source', '?')}",
        "",
    ]
    if decision_context:
        lines.extend([
            "【独立决策验证】",
            f"- 目标: {_short(decision_context.get('label'), 120) or '待获取'}",
            f"- 与C线关系: {_short(decision_context.get('relation_to_c_line'), 220) or '待获取'}",
            f"- 审计说明: {_short(decision_context.get('audit_note'), 220) or '待获取'}",
            "",
        ])
    lines.extend([
        "【C线原始动作/方向/置信度（仅留档）】" if decision_context else "【C线原始动作/方向/置信度】",
        f"- action={c_pred.get('action') or '待获取'}  direction={c_pred.get('direction') or '待获取'}  confidence={_fmt_confidence(c_pred.get('confidence'))}",
        f"- reason={c_reason}",
        "",
        "【LLM客观评价】",
        reasoning or "待获取",
        "",
        "【C线反哺线索】",
        f"- trigger_type={trigger_type}; expected_feedback_to_c={_short(expected_feedback, 220) or '待获取'}",
        f"- 价格位置: MA20偏离 {_fmt_pct_text(values.get('price_vs_ma20_pct'))}; MA5偏离 {_fmt_pct_text(values.get('price_vs_ma5_pct'))}; MA60偏离 {_fmt_pct_text(values.get('price_vs_ma60_pct'))}",
        "",
        "说明: 价格、涨跌幅、振幅、成交额来自盘中 quote；MA偏离由盘中价和EOD均线重算；C线预测与观察任务来自EOD冻结上下文。",
    ])
    return "\n".join(lines)


def notify_market_health(events: List[Dict[str, Any]]) -> None:
    if not events:
        return
    title = "[盘面体检] 高风险异常"
    body = render_market_health_notification(events)
    logger.info("\n%s\n%s\n%s\n%s", "=" * 40, title, body, "=" * 40)
    push_wechat(title, body, pushplus_token=_PUSHPLUS_TOKEN)
    push_email(title, body, smtp_conf=_smtp_conf())


def notify_dline(task: Dict[str, Any], quote: Dict[str, Any], blueprint: Dict[str, Any],
                 values: Dict[str, Any], fire_count=None):
    """Send a D-line alert and freeze the trigger as a forecast row."""
    code = str(task.get("code") or quote.get("code") or "").strip()
    name = task.get("name") or quote.get("name") or code
    obs = task.get("observation") or {}
    evidence = task.get("evidence_pack") or {}
    c_pred = ((evidence.get("C_prediction") or {}).get("prediction") or {})
    trigger_type = blueprint.get("trigger_type") or "dline_trigger"
    severity = blueprint.get("severity") or "medium"
    title = f"[D线] {name} {trigger_type} 触发"
    reasoning = _dline_reasoning(task, blueprint)
    history = evidence.get("B_prediction_history_summary") or {}
    if not history.get("available"):
        from vaxstock.services.history_summary import load_live_history
        evidence["B_prediction_history_summary"] = load_live_history(
            cutoff_trade_date=task.get("baseline_trade_date")
        ).get(code) or history
    from vaxstock.services.daily_action import load_daily_strategy_row
    strategy_row = load_daily_strategy_row(code, task.get("target_trade_date"))
    body = _format_dline_alert_body(
        code, name, task, quote, blueprint, values, c_pred,
        reasoning, trigger_type, severity, fire_count=fire_count,
        strategy_row=strategy_row,
    )

    structured = {
        "verdict": trigger_type,
        "direction": c_pred.get("direction") or "observe",
        "confidence": c_pred.get("confidence"),
        "horizon": "intraday",
        "thesis_tags": ["dline", trigger_type, severity],
        "falsify_if": obs.get("falsify_if") or "",
        "source": "dline_task_blueprint",
        "task_id": task.get("task_id"),
        "fire_count": fire_count,
        "trigger_type": trigger_type,
        "severity": severity,
        "c_line_action": c_pred.get("action"),
        "c_line_direction": c_pred.get("direction"),
        "c_line_confidence": c_pred.get("confidence"),
    }
    inputs_ref = {
        "baseline_date": task.get("baseline_trade_date"),
        "dline_task_id": task.get("task_id"),
        "dline_plan_version": task.get("plan_version"),
        "trigger_blueprint": blueprint,
        "trigger_values": values,
        "quote_snapshot": quote,
        "evidence_pack": evidence,
    }
    written = record_forecast(code, quote.get("trade_date"), f"D-line {trigger_type}: {blueprint.get('why', '')}",
                              inputs_ref, structured, reasoning, structured.get("falsify_if", ""))
    if written:
        evolution = start_trigger_evolution(task, trigger_type, quote)
        if evolution.get("status") not in {"written", "duplicate"}:
            logger.warning(
                "D-line evolution start failed: code=%s task_id=%s result=%s",
                code, task.get("task_id"), evolution,
            )
    logger.info("\n%s\n%s\n%s\n%s", "=" * 40, title, body, "=" * 40)
    push_wechat(title, body, pushplus_token=_PUSHPLUS_TOKEN)
    push_email(title, body, smtp_conf=_smtp_conf())
    if written:
        _maybe_autocommit_intraday_forecast()


def notify(rule, quote, fire_count=None):
    """触发: 控制台+微信+邮箱; 命中后拉快照+T-1基准+大盘背景喂 codex → JSON 预测 → 渲染推送 + 冻结 forecast。

    codex 现出结构化 JSON(verdict/direction/confidence/falsify_if...); 解析失败则降级纯价位告警(不崩)。
    forecast 只收体系内标的(有 T-1 基准 或 在概念池): 池外临时票出研判但不写 forecast(防回测污染)。
    """
    code = rule["code"]
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

    # 命中后: 拉 lite 快照 + T-1 基准 + 概念 + 大盘背景 → codex 假设检验 JSON
    snap = fetch_lite(code)
    t1 = load_t1_baseline(code)
    concepts = _get_concepts(code)
    ctx = None
    raw = None
    if snap:
        ctx = fetch_market_ctx()
        raw = _codex_verdict(snap, rule.get("note", ""), market_ctx=ctx,
                             concepts=concepts, fire_count=fire_count, t1_baseline=t1)

    structured = _parse_codex_json(raw)
    forecast_written = False
    if structured:
        # reasoning 过铁律硬校验(昨日限定词白名单); 回写校验后文本
        reasoning = enforce_intraday_rules(str(structured.get("reasoning", "")))
        structured["reasoning"] = reasoning
        conf = structured.get("confidence")
        conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else "?"
        body += (
            f"\n────────────\n🤖 盘中研判:\n"
            f"状态: {structured.get('verdict', '?')}\n"
            f"方向: {structured.get('direction', '?')}  置信: {conf_str}\n"
            f"{reasoning}\n"
            f"(盘中代理,未定论;评分资金以EOD为准)"
        )
        # 冻结 forecast(池外票 guard): 体系内(有T-1基准 或 在概念池)才写, 防回测样本污染
        in_pool = (t1 is not None) or bool(concepts)
        if in_pool:
            inputs_ref = {
                "baseline_date": (t1 or {}).get("baseline_date"),
                "t1_baseline": t1,
                "lite_snapshot": snap,
                "regime": (ctx or {}).get("regime"),
            }
            written = record_forecast(code, quote.get("trade_date"), rule.get("note", ""),
                                      inputs_ref, structured, reasoning,
                                      structured.get("falsify_if", ""))
            if written:
                forecast_written = True
        else:
            logger.info(f"{code} 池外临时票(无T-1基准且不在概念池): 出研判, 不写 forecast(防回测污染)")
    elif raw:
        logger.warning(f"{code} codex returned non-JSON; trigger alert will still be sent. raw={str(raw)[:80]}")
        body += (
            "\n------------\n"
            "AI研判返回非 JSON，本次已降级为规则触发告警；请以实时盘口和 EOD 基准复核。"
        )
    elif snap:
        logger.warning("%s codex unavailable; trigger alert will still be sent", code)
        body += (
            "\n------------\n"
            "AI研判暂不可用，本次仍按规则触发发送告警；请以实时盘口和 EOD 基准复核。"
        )
    logger.info(f"\n{'='*40}\n🚨 {title}\n{body}\n{'='*40}")
    push_wechat(title, body, pushplus_token=_PUSHPLUS_TOKEN)
    push_email(title, body, smtp_conf=_smtp_conf())
    if forecast_written:
        _maybe_autocommit_intraday_forecast()



def _close_review_target(dline_tasks: List[Dict[str, Any]]) -> Optional[str]:
    targets = {
        str(task.get("target_trade_date") or "").strip()
        for task in dline_tasks or [] if task.get("target_trade_date")
    }
    return next(iter(targets)) if len(targets) == 1 else None


def _dline_trigger_key(task: Dict[str, Any], trigger_type: str):
    return ("dline", task.get("task_id") or task.get("code"), str(trigger_type or ""))


def _existing_dline_runtime_state(dline_tasks: List[Dict[str, Any]]):
    target = _close_review_target(dline_tasks)
    if not target:
        return set(), {}
    try:
        facts_by_code = load_dline_trigger_facts(target)
    except Exception as exc:
        logger.warning("failed to restore D-line fired keys: %s: %s", type(exc).__name__, str(exc)[:160])
        return set(), {}
    task_by_id = {
        str(task.get("task_id") or ""): task for task in dline_tasks if task.get("task_id")
    }
    restored = set()
    fire_counts = {}
    for facts in facts_by_code.values():
        for fact in facts:
            task = task_by_id.get(str(fact.get("task_id") or ""))
            if task is not None:
                restored.add(_dline_trigger_key(task, fact.get("trigger_type")))
                code = str(task.get("code") or "")
                fire_counts[code] = fire_counts.get(code, 0) + 1
    return restored, fire_counts


def _existing_dline_fired_keys(dline_tasks: List[Dict[str, Any]]):
    return _existing_dline_runtime_state(dline_tasks)[0]


def _run_close_review(dline_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    target = _close_review_target(dline_tasks)
    if not target:
        return {"status": "skipped", "reason": "target_trade_date_missing_or_mixed"}
    from vaxstock.services.daily_action import refresh_and_send_close_review
    evolution_result = finalize_evolutions(target)
    if evolution_result.get("status") not in {"finalized", "missing"}:
        logger.warning(
            "D-line evolution finalization incomplete: target=%s result=%s",
            target, evolution_result,
        )
    coverage_result = finalize_observation_coverage(target)
    if coverage_result.get("status") not in {"finalized"}:
        logger.warning(
            "D-line coverage finalization incomplete: target=%s result=%s",
            target, coverage_result,
        )
    codes = sorted(
        {str(task.get("code") or "") for task in dline_tasks if task.get("code")}
        | set(config.load_holdings())
    )

    def _load_close_quotes():
        return fetch_quotes(codes) or {}

    result = refresh_and_send_close_review(
        target_trade_date=target,
        reference_quote_loader=_load_close_quotes,
    )
    logger.info("Close review completed: target=%s action=%s mail=%s", target,
                (result.get("action") or {}).get("status"), result.get("mail"))
    return result


# ==================== 主循环 ====================

def run(once=False, force=False):
    holding_codes = set(config.load_holdings())
    rules = load_rules(holding_codes)
    dline_tasks = load_dline_tasks(holding_codes=holding_codes)
    restore_active_evolutions(dline_tasks)
    fired_keys, today_fire_count = _existing_dline_runtime_state(dline_tasks)
    fire_count_day = None

    def _rule_key(r):
        return ("legacy", r.get("code"), r.get("type"), r.get("level"))


    def _active_codes():
        legacy_codes = {r.get("code") for r in rules if r.get("code")}
        dline_codes = {t.get("code") for t in dline_tasks if t.get("code")}
        holding_codes = set(config.load_holdings())
        return sorted(legacy_codes | dline_codes | holding_codes)

    codes = _active_codes()
    logger.info("intraday watch started. legacy_rules=%s dline_tasks=%s codes=%s", len(rules), len(dline_tasks), codes)
    chans = []
    if _PUSHPLUS_TOKEN:
        chans.append("wechat")
    if _smtp_conf():
        chans.append("email")
    logger.info("poll=%ss push_channels=%s dline_file=%s watch_rules=%s",
                POLL_SECONDS, "+".join(chans) if chans else "console-only", DLINE_TASKS_FILE, WATCH_RULES_FILE)

    try:
        with request.urlopen(f"{API_BASE}/health", timeout=10) as r:
            h = json.loads(r.read().decode("utf-8"))
            logger.info(f"/health ok: regime={h.get('regime')} tushare={h.get('tushare_points')}")
    except Exception as e:
        logger.warning(f"service health probe failed: {e} (continue intraday polling)")

    while True:
        _today = dt.date.today()
        if _today != fire_count_day:
            today_fire_count.clear()
            fired_keys.clear()
            restored_keys, restored_counts = _existing_dline_runtime_state(dline_tasks)
            fired_keys.update(restored_keys)
            today_fire_count.update(restored_counts)
            fire_count_day = _today

        if not is_trading_time(force):
            n = dt.datetime.now()
            if n.time() > dt.time(15, 2):
                try:
                    _run_close_review(dline_tasks)
                except Exception as exc:
                    logger.warning("close review failed, will retry after poll interval: %s: %s",
                                   type(exc).__name__, str(exc)[:160])
                if once:
                    break
                time.sleep(POLL_SECONDS)
                continue
            logger.info("outside trading window, waiting...")
            if once:
                break
            time.sleep(POLL_SECONDS)
            continue

        holding_codes = set(config.load_holdings())
        new_rules = load_rules(holding_codes)
        for r in new_rules:
            r["fired"] = _rule_key(r) in fired_keys
        rules = new_rules
        loaded_dline_tasks = load_dline_tasks(holding_codes=holding_codes)
        previous_task_ids = {str(task.get("task_id") or "") for task in dline_tasks}
        loaded_task_ids = {str(task.get("task_id") or "") for task in loaded_dline_tasks}
        dline_tasks = loaded_dline_tasks
        if loaded_task_ids != previous_task_ids:
            restore_active_evolutions(dline_tasks)
            restored_keys, restored_counts = _existing_dline_runtime_state(dline_tasks)
            fired_keys.update(restored_keys)
            for code, count in restored_counts.items():
                today_fire_count[code] = max(today_fire_count.get(code, 0), count)
        codes = _active_codes()
        if not codes:
            logger.info("no legacy rules and no D-line tasks for today; no-op")
            if once:
                break
            time.sleep(POLL_SECONDS)
            continue

        data = fetch_quotes(codes)
        if data:
            line = []
            for c in codes:
                qd = data.get(c, {})
                if qd:
                    line.append(f"{qd.get('name', c)} {qd.get('price')}({qd.get('change_pct', 0):+.1f}%)")
            if line:
                logger.info(" | ".join(line))

            try:
                health = run_market_health_check(
                    quotes=data,
                    holdings=config.load_holdings(),
                    tasks=dline_tasks,
                    market_ctx_loader=fetch_market_ctx,
                    force=force,
                )
                if health.get("notifications"):
                    notify_market_health(health["notifications"])
                if health.get("status") in {
                    "insufficient_data", "invalid_state",
                    "invalid_observed_at", "invalid_events",
                }:
                    logger.warning("market health check did not conclude: %s", health)
            except Exception as exc:
                logger.warning("market health check failed: %s: %s",
                               type(exc).__name__, str(exc)[:160])

            for rule in rules:
                if rule.get("fired"):
                    continue
                qd = data.get(rule.get("code"))
                if not qd:
                    continue
                if check_rule(rule, qd):
                    code = rule["code"]
                    today_fire_count[code] = today_fire_count.get(code, 0) + 1
                    notify(rule, qd, fire_count=today_fire_count.get(code, 1))
                    rule["fired"] = True
                    fired_keys.add(_rule_key(rule))

            for task in dline_tasks:
                code = task.get("code")
                qd = data.get(code)
                if not qd:
                    continue
                coverage = record_task_observation(
                    task, qd, observed_at=dt.datetime.now().isoformat(timespec="seconds"),
                )
                if coverage.get("status") == "error":
                    logger.warning("D-line coverage write failed: code=%s task_id=%s detail=%s",
                                   code, task.get("task_id"), coverage.get("detail"))
                evolution = record_evolution_observation(
                    task, qd, observed_at=dt.datetime.now().isoformat(timespec="seconds"),
                )
                if evolution.get("status") == "error":
                    logger.warning("D-line evolution write failed: code=%s task_id=%s detail=%s",
                                   code, task.get("task_id"), evolution.get("detail"))
                for idx, bp, values in matching_dline_triggers(task, qd):
                    key = _dline_trigger_key(task, bp.get("trigger_type"))
                    if key in fired_keys:
                        continue
                    today_fire_count[code] = today_fire_count.get(code, 0) + 1
                    logger.info("D-line trigger matched: code=%s task_id=%s blueprint_index=%s trigger_type=%s",
                                code, task.get("task_id"), idx, bp.get("trigger_type"))
                    notify_dline(task, qd, bp, values, fire_count=today_fire_count.get(code, 1))
                    fired_keys.add(key)

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
