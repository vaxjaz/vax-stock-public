"""
盘中 N 票实时分析 HTTP API —— 复用 stock_report_enhanced 现有逻辑,零 MCP 依赖。
放在 /opt/stock-report/ 下与现有 .py 同目录运行。

端点(均只读,无写操作):
  GET /health                      返回 regime / tushare 点数 / 今日次数。
  GET /quote?codes=600276,600900   多票实时报价(Sina,秒级)。
  GET /market                      强制刷新并返回大盘 regime + 涨跌家数。
  GET /analyze/{code}              单票四维(build_stock_item 完整流水线 + v1.2评分)。

安全模型(方案②: 查询端点免鉴权):
  返回均为公开行情衍生指标, 无持仓/无 PII。靠 DuckDNS 域名难枚举 +
  每日 analyze 次数封顶兜底。token 不经过任何对话/URL/project。
"""
import os
import json
import time
import threading
from datetime import date
from pydantic import BaseModel
from typing import Optional, List

from fastapi import FastAPI, Header, HTTPException, Query, Body
from fastapi.responses import JSONResponse

import stock_report_enhanced as R   # 导入即自动 init TUSHARE(模块级)

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

# ---------- 大盘 regime 缓存(评分依赖,5分钟刷新) ----------
REGIME_TTL = int(os.environ.get("REGIME_TTL", "300"))
_regime_lock = threading.Lock()
_regime_state = {"ts": 0.0, "regime": "momentum", "overview": {}}

def refresh_regime(force=False):
    with _regime_lock:
        if not force and (time.time() - _regime_state["ts"] < REGIME_TTL):
            return _regime_state
        indices = []
        for symbol, name in R.INDEX_LIST:
            idx = R.get_sina_index(symbol, name)
            if idx:
                indices.append(idx)
            time.sleep(getattr(R, "REQUEST_SLEEP_SECONDS", 0.2))
        overview = R.get_em_market_overview()
        regime = R.detect_market_regime(indices, overview)
        R._CURRENT_MARKET_REGIME = regime          # 写回模块全局,build_stock_item 评分会读它
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
    return {
        "ok": True,
        "regime": R._CURRENT_MARKET_REGIME,
        "tushare_points": R.TUSHARE.points_level if R.TUSHARE else 0,
        "analyze_today": _cap["count"],
    }

@app.get("/quote")
def quote(codes: str = Query(...)):
    out = {}
    for c in [x.strip() for x in codes.split(",") if x.strip()]:
        out[c] = R.get_sina_realtime(c, "")
    return JSONResponse(_safe(out))

@app.get("/market")
def market():
    st = refresh_regime(force=True)
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
    rt = R.get_sina_realtime(code, "")
    hist = R.get_history_kline(code)
    m = R.calc_derived_metrics(rt, hist, None, None, None, None)  # 不传 money_flow/quarterly
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
        # lite 输出不含 regime, 故跳过 refresh_regime()(冷缓存时它会扫全市场,
        # 曾导致 lite 被拖到 2 分钟+)。lite 只做 实时+历史K线, ~3s。
        return JSONResponse(_safe(build_lite_item(code)))
    refresh_regime()                  # 确保 regime 已算(5分钟缓存)
    _bump_cap()
    item = R.build_stock_item("watch", code, "", None, None)
    return JSONResponse(_safe(item))

WATCH_RULES_FILE = os.environ.get("WATCH_RULES_FILE", "watch_rules.json")
_rules_lock = threading.Lock()
_VALID_TYPES = {"price_above", "price_below", "pct_above", "pct_below"}

# --- 鉴权钩子(当前关闭, 后续打开) ---
WATCH_WRITE_KEY = os.environ.get("WATCH_WRITE_KEY", "")   # 设了环境变量即启用
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
    os.replace(tmp, WATCH_RULES_FILE)   # 原子替换, 防写一半被读

class WatchRule(BaseModel):
    code: str
    name: str
    type: str
    level: float
    note: str = ""

# 注: app 在主文件已定义, 这里直接用同名 app
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