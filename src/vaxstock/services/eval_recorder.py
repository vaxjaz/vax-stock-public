# -*- coding: utf-8 -*-
"""services 层: MR-Eval 预测追踪数据地基(E1)。

全 watchlist 因子快照 append-only 记录 + T+k 真实后续收益回填。预测追踪反哺的源头数据,
越早记越值钱(数据时间不可逆)。run_eod 在落盘后调 record_and_backfill(payload, source)。

【设计铁律(CLAUDE.md §9.7)】
  - 全 watchlist 无条件每票记(holding+watchlist 全记, 防幸存者偏差, 非只记触发的);
  - append-only: 预测先于结果冻结。snapshots.jsonl 严格只增不改;
  - 每条快照带"当时的世界状态"(regime/宏观/宽度/北向/赛道/指数), 用于按状态分桶 / 剔除特殊期;
  - 回填用 Tushare 真收盘机械算 + 指数基准算超额, 无主观;
  - 交易日锚 payload trade_date(§9.1), 不用 now()。

【append-only 纯净拆分(关键决策)】
  预测 = factor_snapshots.jsonl(冻结不动); 结果 = factor_results.jsonl(单独 append)。
  回填绝不改 snapshots(否则"回填时改预测"嫌疑); 分析时两文件按 (trade_date, code) join。
  results 行带 complete 标记(全 horizon 是否填满); 仅当新增 horizon 才 append(防每日重复 spam),
  已 complete 的 key 不再回填。
"""

import datetime as dt
import json
import logging
from pathlib import Path

from vaxstock import config

logger = logging.getLogger(__name__)

# 落 config.STATE_DIR/eval/(已 gitignore 的 var/ 下); 测试可 monkeypatch 这两个模块级路径到 tmp
EVAL_DIR = config.STATE_DIR / "eval"
SNAPSHOTS_FILE = EVAL_DIR / "factor_snapshots.jsonl"
RESULTS_FILE = EVAL_DIR / "factor_results.jsonl"

BENCHMARK_INDEX = "000001.SH"   # 上证综指(算超额的基准)
DEFAULT_HORIZONS = (1, 3, 5, 10, 20, 30)
SCHEMA_VERSION = 1


# ==================== jsonl 读写(原子 append, 只增不改) ====================

def _now_iso() -> str:
    """生成时刻戳(ISO)。仅作记录时刻, 非交易日基准(§9.1)。"""
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                logger.warning(f"eval jsonl 行解析失败, 跳过: {line[:60]}")
    return rows


def _append_jsonl(path, row) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


# ==================== 市场状态提取(快照里的"当时的世界") ====================

def _macro_state(macro):
    """从 payload['macro'] 提 (macro_regime, 6维 signal 摘要); 不可用/缺 -> (None, {available:False})。"""
    macro = macro or {}
    if macro.get("available") is False or not macro.get("macro_regime"):
        return None, {"available": False}
    ind = macro.get("indicators") or {}

    def sig(key, sub="signal"):
        return (ind.get(key) or {}).get(sub)

    breadth = ind.get("breadth") or {}
    signals = {
        "etf": sig("etf_net_sub", "signal_5d"),
        "margin": sig("margin_ratio"),
        "turnover": sig("turnover"),
        "erp": sig("hs300_erp"),
        "m1": sig("m1_yoy"),
        "breadth": "待" if breadth.get("available") is False else sig("breadth"),
    }
    return macro.get("macro_regime"), signals


def _market_state(payload) -> dict:
    """快照随附的市场状态(按"世界状态"分桶 / 剔除特殊期用)。"""
    mo = payload.get("market_overview") or {}
    macro_regime, macro_signals = _macro_state(payload.get("macro"))

    tracks = payload.get("tracks") or []
    ai_track = None
    if tracks:
        t0 = tracks[0] or {}
        ai_track = {
            "track_name": t0.get("track_name"),
            "position_ceiling": t0.get("position_ceiling"),
            "available": t0.get("available"),
        }

    idx_snap = {}
    for idx in payload.get("indices") or []:
        nm = idx.get("name") or idx.get("symbol")
        if nm:
            idx_snap[nm] = {"close": idx.get("price"), "change_pct": idx.get("change_pct")}

    return {
        "regime": payload.get("market_regime"),
        "breadth": {
            "up_count": mo.get("up_count"),
            "down_count": mo.get("down_count"),
            "limit_up_count": mo.get("limit_up_count"),
            "limit_down_count": mo.get("limit_down_count"),
        },
        "north_flow": payload.get("north_flow"),
        "macro_regime": macro_regime,
        "macro_signals": macro_signals,
        "ai_track": ai_track,
        "index_snapshot": idx_snap,
    }


# ==================== (1) 当日全 watchlist 快照 append ====================

def record_snapshots(payload) -> int:
    """当日全 watchlist(holding+watchlist)快照 append 到 snapshots.jsonl。返回新增条数。

    交易日锚 payload market_overview.trade_date(§9.1); 缺则跳过本次(不臆造日期污染序列)。
    幂等: 同 (trade_date, code) 已存在则跳过(同日 EOD 跑 N 次不重复记)。
    """
    td = (payload.get("market_overview") or {}).get("trade_date")
    if not td:
        logger.warning("payload 无 trade_date, MR-Eval 跳过本次快照(不臆造日期)")
        return 0
    td = str(td)

    # 幂等: 已记录的 (td, code) 集合
    existing = {r.get("code") for r in _read_jsonl(SNAPSHOTS_FILE) if str(r.get("trade_date")) == td}

    market = _market_state(payload)
    snapshot_ts = _now_iso()
    written = 0
    for item in payload.get("stocks") or []:
        code = item.get("code")
        if not code or code in existing:
            continue  # 幂等: 同日同票不重复
        rt = item.get("realtime") or {}
        row = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_ts": snapshot_ts,
            "trade_date": td,
            "code": code,
            "name": rt.get("name") or item.get("configured_name"),
            "group": item.get("group"),
            "concepts": item.get("concepts", []),
            "price_at_snapshot": rt.get("price"),   # 基准锚价(算后续收益的分母)
            "metrics": item.get("metrics") or {},   # 全量因子(宁全勿缺)
            "market": market,                        # 当时的世界状态
            # —— 结果占位, 真结果走 results.jsonl(snapshots 冻结不改)——
            "filled": False,
            "ret": {}, "mkt_ret": {}, "excess": {}, "filled_ts": None,
        }
        _append_jsonl(SNAPSHOTS_FILE, row)
        existing.add(code)
        written += 1
    logger.info(f"MR-Eval 快照: trade_date={td} 新增 {written} 条(全 watchlist)")
    return written


# ==================== (2) T+k 回填(结果单独 append, 不改预测) ====================

def _benchmark_closes(source) -> dict:
    """取基准指数(上证综指)近 ~400 日 {trade_date: close}; 取不到返 {}(不臆造)。

    get_index_daily 只返最新一行, 故走 source._safe_call('index_daily', 区间) 拉序列。
    测试可直接 monkeypatch 本函数返回构造序列(零网络)。
    """
    try:
        end = dt.datetime.now().strftime("%Y%m%d")
        start = (dt.datetime.now() - dt.timedelta(days=400)).strftime("%Y%m%d")
        df = source._safe_call("index_daily", ts_code=BENCHMARK_INDEX,
                               start_date=start, end_date=end, fields="trade_date,close")
        if df is None:
            return {}
        out = {}
        for rec in df.to_dict("records"):
            d = str(rec.get("trade_date")).strip()
            if d.endswith(".0"):
                d = d[:-2]
            c = rec.get("close")
            if c is not None:
                out[d] = float(c)
        return out
    except Exception as e:
        logger.warning(f"MR-Eval 基准指数序列取数失败: {str(e)[:80]}")
        return {}


def backfill(source, horizons=DEFAULT_HORIZONS) -> int:
    """给 snapshots 里尚未 complete 的 (trade_date, code) 回填真实 T+k 收益/超额, append 到 results.jsonl。

    机械算: ret_k = close[idx0+k]/price_at_snapshot - 1; mkt_ret_k = 指数同窗收益; excess_k = ret_k - mkt_ret_k。
    天数不足 / 指数缺 → 该 horizon 跳过(不臆造)。只增不改 snapshots; results 仅在"新增 horizon"时 append(防 spam)。
    返回新增 results 行数。
    """
    snaps = _read_jsonl(SNAPSHOTS_FILE)
    if not snaps:
        return 0

    # 已有 results: 每 (td,code) 取最新行的已填 horizon 集合 + complete 标记
    done = {}            # (td,code) -> set(已填 horizon)
    complete_keys = set()
    for r in _read_jsonl(RESULTS_FILE):
        key = (str(r.get("trade_date")), r.get("code"))
        done[key] = {int(h) for h in (r.get("ret") or {}).keys()}
        if r.get("complete"):
            complete_keys.add(key)

    target = set(horizons)
    bench = None  # 懒取一次(覆盖所有快照日期)
    new_rows = []
    for s in snaps:
        td = str(s.get("trade_date"))
        code = s.get("code")
        key = (td, code)
        if key in complete_keys:
            continue
        price0 = s.get("price_at_snapshot")
        if not price0:   # 无基准锚价(None/0)无法算收益
            continue

        kl = source.get_daily_kline(code, days=250)
        if not kl:
            continue
        dates = [str(r.get("trade_date")).split(".")[0] for r in kl]   # 升序
        closes = [r.get("close") for r in kl]
        if td not in dates:
            continue
        idx0 = dates.index(td)

        if bench is None:
            bench = _benchmark_closes(source)
        base_bench = bench.get(td)

        ret, mkt, excess = {}, {}, {}
        for k in horizons:
            j = idx0 + k
            if j >= len(closes) or closes[j] is None:
                continue  # 天数不足 -> 跳过该 horizon
            ret_k = float(closes[j]) / float(price0) - 1.0
            ret[str(k)] = ret_k
            td_k = dates[j]
            if base_bench and bench.get(td_k):
                mkt_k = bench[td_k] / base_bench - 1.0
                mkt[str(k)] = mkt_k
                excess[str(k)] = ret_k - mkt_k

        filled_hs = {int(h) for h in ret.keys()}
        if not filled_hs or filled_hs == done.get(key, set()):
            continue  # 无新增 horizon -> 不重复 append
        new_rows.append({
            "trade_date": td, "code": code,
            "ret": ret, "mkt_ret": mkt, "excess": excess,
            "complete": target.issubset(filled_hs),
            "filled_ts": _now_iso(),
        })

    for row in new_rows:
        _append_jsonl(RESULTS_FILE, row)
    if new_rows:
        logger.info(f"MR-Eval 回填: 新增/更新 {len(new_rows)} 条结果(results.jsonl)")
    return len(new_rows)


# ==================== (3) 编排: 先回填后记录 ====================

def record_and_backfill(payload, source) -> dict:
    """先 backfill(补历史快照结果)再 record_snapshots(记当日)。

    顺序: 先回填后记录 —— 避免当天刚记的快照立刻被当未回填扫(当天无未来交易日, 本也填不了)。
    """
    n_filled = backfill(source)
    n_snap = record_snapshots(payload)
    return {"backfilled": n_filled, "snapshots": n_snap}
