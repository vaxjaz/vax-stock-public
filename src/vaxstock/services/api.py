# -*- coding: utf-8 -*-
"""盘中实时分析 HTTP API(services 层, v2 重构版)。

MR6 PR-C1: 由 monolith script/api.py 迁入。禁止 import monolith(stock_report_enhanced / R),
全部走 v2 包内 seam。去模块级副作用:
  - 顶层不构造 client、不连网; TushareSource 走惰性加锁单例 _get_source()(首次用时建)
  - 消全局 _CURRENT_MARKET_REGIME: refresh_regime 算出 regime 只存进 _regime_state 缓存,
    analyze 非 lite 分支把 regime 显式传 build_stock_item(..., market_regime=...)

端点(8 个): /health /quote /market /analyze/{code}(lite=1 前置) /watch/{list,add,clear,replace}
安全模型(沿用): 查询端点免鉴权(均为公开行情衍生指标, 无持仓/PII); watch 写操作经 _check_key + 每日配额兜底。
"""

import json
import os
import threading
import time
from datetime import date
from typing import List, Optional

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vaxstock import config
from vaxstock.services import pool_admin
from vaxstock.analysis.stock_item import build_stock_item
from vaxstock.indicators.regime import detect_market_regime
from vaxstock.indicators.scoring import calc_derived_metrics
from vaxstock.sources.market import get_market_overview
from vaxstock.sources.sina import get_sina_index, get_sina_realtime
from vaxstock.sources.tushare_src import TushareSource, get_history_kline


# ---------- TushareSource 惰性加锁单例(不在 import 时构造, 不连网) ----------
_src_lock = threading.Lock()
_src = None


def _get_source():
    global _src
    with _src_lock:
        if _src is None:
            _src = TushareSource(config.SECRETS.get("tushare_token"))
        return _src


# ---------- Tushare 每日次数封顶(防滥用烧配额) ----------
MAX_ANALYZE_PER_DAY = int(os.environ.get("MAX_ANALYZE_PER_DAY", "300"))
_cap_lock = threading.Lock()
_cap = {"day": None, "count": 0}


def _bump_cap():
    with _cap_lock:
        today = str(date.today())
        if _cap["day"] != today:
            _cap["day"], _cap["count"] = today, 0
        if _cap["count"] >= MAX_ANALYZE_PER_DAY:
            raise HTTPException(429, f"今日 analyze 已达上限 {MAX_ANALYZE_PER_DAY}")
        _cap["count"] += 1


# ---------- 大盘 regime 缓存(评分依赖, 5分钟刷新); 不写任何模块全局 ----------
REGIME_TTL = int(os.environ.get("REGIME_TTL", "300"))
_regime_lock = threading.Lock()
_regime_state = {"ts": 0.0, "regime": "momentum", "overview": {}}


def refresh_regime(force=False):
    """刷新并缓存大盘 regime。指数走新浪(盘中秒级), 涨跌家数走 Tushare 全市场(get_market_overview)。
    结果只存 _regime_state, 绝不写 _CURRENT_MARKET_REGIME 全局, 不调用 monolith。"""
    with _regime_lock:
        if not force and (time.time() - _regime_state["ts"] < REGIME_TTL):
            return _regime_state
        indices = []
        for symbol, name in config.INDEX_LIST:
            idx = get_sina_index(symbol, name)
            if idx:
                indices.append(idx)
            time.sleep(config.REQUEST_SLEEP_SECONDS)
        overview = get_market_overview(_get_source())
        regime = detect_market_regime(indices, overview)
        _regime_state.update(ts=time.time(), regime=regime, overview=overview)
        return _regime_state


# ---------- JSON 安全化(numpy 等类型兜底) ----------
def _safe(obj):
    return json.loads(json.dumps(
        obj, ensure_ascii=False,
        default=lambda o: float(o) if hasattr(o, "__float__") else str(o)))


# ---------- 应用 ----------
app = FastAPI(title="stock intraday api", docs_url=None, redoc_url=None)


@app.get("/health")
def health():
    with _src_lock:
        pts = _src.points_level if _src is not None else 0  # 不强制构造, 仅 peek
    return {
        "ok": True,
        "regime": _regime_state["regime"],   # 读缓存, 非全局
        "tushare_points": pts,
        "analyze_today": _cap["count"],
    }


@app.get("/quote")
def quote(codes: str = Query(...)):
    out = {}
    for c in [x.strip() for x in codes.split(",") if x.strip()]:
        out[c] = get_sina_realtime(c, "")
    return JSONResponse(_safe(out))


@app.get("/market")
def market():
    st = refresh_regime()  # 走 REGIME_TTL 缓存(与 monolith 一致); force 全市场重扫会烧配额且与 lite 防冷扫意图相悖
    return JSONResponse(_safe({"regime": st["regime"], "overview": st["overview"]}))


# 盘中 lite 快照保留的价量维度(均来自 实时+历史K线, 不依赖结算价/不含资金/不含评分)
_LITE_METRIC_KEYS = [
    "ma5", "ma10", "ma20", "ma60", "ma_trend",
    "price_vs_ma5_pct", "price_vs_ma20_pct", "price_vs_ma60_pct",
    "volume_ratio_5d", "position_20d_pct", "position_52w_pct",
    "recent_5d_change_pct", "recent_20d_change_pct",
    "macd_dif", "macd_dea", "macd_hist", "rsi_14",
]


def build_lite_item(code: str) -> dict:
    """盘中极速快照: 仅 实时行情 + 历史K线衍生(MA/位置/振幅/量比/技术),
    严格剔除 right_side_score 系列(14_intraday_protocol 铁规: 盘中不发布评分)
    与 T-1 滞后的主力资金流(避免被当成实时)。约 2 次网络调用。"""
    rt = get_sina_realtime(code, "")
    hist = get_history_kline(_get_source(), code)
    m = calc_derived_metrics(rt, hist, None, None, None, None)  # 不传 money_flow/quarterly
    metrics_lite = {k: m.get(k) for k in _LITE_METRIC_KEYS}
    return {
        "code": code,
        "name": (rt or {}).get("name", ""),
        "as_of": (rt or {}).get("trade_time", ""),
        "price": (rt or {}).get("price"),
        "change_pct": (rt or {}).get("change_pct"),
        "amplitude_pct": (rt or {}).get("amplitude_pct"),
        "amount_yi": round(((rt or {}).get("amount") or 0) / 1e8, 2),
        "metrics": metrics_lite,
        "_note": ("盘中实时代理值; 已剔除 right_side_score 与 T-1 滞后资金流; "
                  "任何结论须标注'盘中未定论', 不得输出买卖价格指令"),
    }


@app.get("/analyze/{code}")
def analyze(code: str, lite: int = Query(0)):
    if lite:
        # lite 输出不含 regime, 必须在 refresh_regime() 之前 return:
        # 冷缓存时 refresh_regime 会扫全市场, 曾把 lite 拖到 2 分钟+。lite 只做 实时+历史K线, ~3s。
        return JSONResponse(_safe(build_lite_item(code)))
    st = refresh_regime()  # 确保 regime 已算(5分钟缓存)
    _bump_cap()
    item = build_stock_item("watch", code, "", None, None,
                            source=_get_source(), market_regime=st["regime"])  # regime 显式传, 非全局
    return JSONResponse(_safe(item))


# ---------- watch 规则(原子读写) ----------
WATCH_RULES_FILE = os.environ.get("WATCH_RULES_FILE") or str(config.STATE_DIR / "watch_rules.json")
_rules_lock = threading.Lock()
_VALID_TYPES = {"price_above", "price_below", "pct_above", "pct_below"}

# --- 鉴权钩子(设了环境变量即启用) ---
WATCH_WRITE_KEY = os.environ.get("WATCH_WRITE_KEY", "")


def _check_key(x_watch_key: Optional[str]):
    if WATCH_WRITE_KEY and x_watch_key != WATCH_WRITE_KEY:
        raise HTTPException(401, "invalid watch key")


def _read_rules():
    try:
        with open(WATCH_RULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        raise HTTPException(500, f"读规则文件失败: {e}")


def _write_rules(rules):
    tmp = WATCH_RULES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    os.replace(tmp, WATCH_RULES_FILE)  # 原子替换, 防写一半被读


class WatchRule(BaseModel):
    code: str
    name: str
    type: str
    level: float
    note: str = ""


@app.get("/watch/list")
def watch_list():
    return JSONResponse(_safe(_read_rules()))


@app.post("/watch/add")
def watch_add(rule: WatchRule, x_watch_key: Optional[str] = Header(None)):
    _check_key(x_watch_key)
    if rule.type not in _VALID_TYPES:
        raise HTTPException(422, f"type须为 {_VALID_TYPES}")
    with _rules_lock:
        rules = _read_rules()
        # 去重: 同 code+type+level 视为同一规则, 覆盖 note
        rules = [r for r in rules if not (
                r.get("code") == rule.code and r.get("type") == rule.type
                and float(r.get("level", -1)) == rule.level)]
        rules.append(rule.dict())
        _write_rules(rules)
    return {"ok": True, "count": len(rules), "added": rule.dict()}


@app.post("/watch/clear")
def watch_clear(code: Optional[str] = None, x_watch_key: Optional[str] = Header(None)):
    _check_key(x_watch_key)
    with _rules_lock:
        rules = _read_rules()
        if code:
            kept = [r for r in rules if r.get("code") != code]
            removed = len(rules) - len(kept)
            _write_rules(kept)
            return {"ok": True, "removed": removed, "remaining": len(kept)}
        else:
            _write_rules([])
            return {"ok": True, "removed": len(rules), "remaining": 0}


@app.post("/watch/replace")
def watch_replace(rules: List[WatchRule] = Body(...), x_watch_key: Optional[str] = Header(None)):
    _check_key(x_watch_key)
    for r in rules:
        if r.type not in _VALID_TYPES:
            raise HTTPException(422, f"{r.code} type非法: {r.type}")
    with _rules_lock:
        data = [r.dict() for r in rules]
        _write_rules(data)
    return {"ok": True, "count": len(data)}


# ---------- 观察池管理 GET-API(便于 Claude 经 web_fetch 调用; 二段式 confirm + 限速 + 审计) ----------
# [P1] token+HTTP 裸奔为临时方案(域名 HTTP, 固定 WATCH_WRITE_KEY), 用户已知并接受; 后续 MCP+HTTPS 收口。
_POOL_RATE_MAX = 20            # 写端点每分钟上限
_pool_calls: List[float] = []  # 滑窗时间戳
_pool_rate_lock = threading.Lock()


def _check_pool_key(token: Optional[str], x_watch_key: Optional[str]) -> None:
    """池端点鉴权: 复用 WATCH_WRITE_KEY。未配 -> 503(整个池 API 关闭); token 不符 -> 401。
    token 从 ?token= 或 X-Watch-Key header 任一取(Claude web_fetch 只能 GET, 故支持 query token)。"""
    if not WATCH_WRITE_KEY:
        raise HTTPException(503, "池管理 API 未启用: 未配置 WATCH_WRITE_KEY(临时方案, 设环境变量启用)")
    if (token or x_watch_key) != WATCH_WRITE_KEY:
        raise HTTPException(401, "invalid pool key")


def _pool_rate_check() -> None:
    """写端点内存限速: 每分钟 ≤ _POOL_RATE_MAX 次, 超限 429。"""
    with _pool_rate_lock:
        now = time.time()
        _pool_calls[:] = [t for t in _pool_calls if now - t < 60]
        if len(_pool_calls) >= _POOL_RATE_MAX:
            raise HTTPException(429, f"池写操作限速: 每分钟 ≤ {_POOL_RATE_MAX} 次")
        _pool_calls.append(now)


def _split_concepts(concepts: Optional[str]) -> List[str]:
    """逗号分隔字符串 -> list; None/空 -> []。"""
    if not concepts:
        return []
    return [c.strip() for c in concepts.replace("，", ",").split(",") if c.strip()]


@app.get("/pool/list")
def pool_list(token: Optional[str] = Query(None), x_watch_key: Optional[str] = Header(None)):
    _check_pool_key(token, x_watch_key)
    return JSONResponse(_safe({"ok": True, "action": "list", "detail": pool_admin.list_pool()}))


@app.get("/pool/propose")
def pool_propose(action: str = Query(...), code: str = Query(...),
                 concepts: Optional[str] = Query(None),
                 token: Optional[str] = Query(None), x_watch_key: Optional[str] = Header(None)):
    """二段式第一步: 回显将写入内容, 不落盘。本期只支持 action=add。"""
    _check_pool_key(token, x_watch_key)
    if action != "add":
        return JSONResponse({"ok": False, "action": action, "error": "propose 仅支持 action=add"})
    preview = pool_admin.propose_add(code, _split_concepts(concepts), source=_get_source())
    return JSONResponse(_safe({"ok": True, "action": "propose_add", "code": code, "preview": preview}))


@app.get("/pool/commit")
def pool_commit(action: str = Query(...), code: str = Query(...),
                concepts: Optional[str] = Query(None),
                token: Optional[str] = Query(None), x_watch_key: Optional[str] = Header(None)):
    """二段式第二步: 真写入 + 审计。action=add|remove|update_concepts。"""
    _check_pool_key(token, x_watch_key)
    _pool_rate_check()
    cs = _split_concepts(concepts)
    try:
        if action == "add":
            pool_admin.commit_add(code, cs, source=_get_source())
        elif action == "remove":
            pool_admin.remove(code)
        elif action == "update_concepts":
            pool_admin.update_concepts(code, cs)
        else:
            return JSONResponse({"ok": False, "action": action,
                                 "error": "action 须为 add|remove|update_concepts"})
    except pool_admin.PoolError as e:
        return JSONResponse({"ok": False, "action": action, "code": code, "error": str(e)})
    return JSONResponse(_safe({"ok": True, "action": action, "code": code,
                               "detail": pool_admin.list_pool()}))


@app.get("/pool/focus")
def pool_focus(concepts: Optional[str] = Query(None),
               token: Optional[str] = Query(None), x_watch_key: Optional[str] = Header(None)):
    """改 hot_sectors(关心的热门赛道); concepts 逗号分隔, 空=清空 focus。"""
    _check_pool_key(token, x_watch_key)
    _pool_rate_check()
    try:
        pool_admin.set_focus(_split_concepts(concepts))
    except pool_admin.PoolError as e:
        return JSONResponse({"ok": False, "action": "set_focus", "error": str(e)})
    return JSONResponse(_safe({"ok": True, "action": "set_focus",
                               "detail": pool_admin.list_pool()["focus"]}))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("API_PORT", "80")))
