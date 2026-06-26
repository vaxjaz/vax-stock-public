# -*- coding: utf-8 -*-
"""services.eval_recorder 测试(MR-Eval E1, 纯函数/jsonl 落 tmp, 零网络)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/services/test_eval_recorder.py -q
     PYTHONPATH=src python3 tests/services/test_eval_recorder.py   # 无 pytest
"""

import datetime as dt
import logging
import pathlib
import shutil
import tempfile
import types

import vaxstock.services.eval_recorder as er


def _set_tmp(d):
    """把 jsonl 路径指到 tmp; 返回 (saved_snap, saved_res) 供恢复。"""
    saved = (er.SNAPSHOTS_FILE, er.RESULTS_FILE)
    er.SNAPSHOTS_FILE = pathlib.Path(d) / "factor_snapshots.jsonl"
    er.RESULTS_FILE = pathlib.Path(d) / "factor_results.jsonl"
    return saved


def _restore(saved):
    er.SNAPSHOTS_FILE, er.RESULTS_FILE = saved


def _payload(td="20260625"):
    return {
        "generated_at": "2026-06-26 05:00",
        "market_regime": "momentum",
        "market_overview": {"trade_date": td, "up_count": 3000, "down_count": 1800,
                            "limit_up_count": 40, "limit_down_count": 5},
        "north_flow": {"total_inflow": 12.3, "is_today": True},
        "macro": {"macro_regime": "🔴 看空", "indicators": {
            "etf_net_sub": {"signal_5d": "❌❌"}, "margin_ratio": {"signal": "⚠️"},
            "turnover": {"signal": "❌❌"}, "hs300_erp": {"signal": "❌❌"},
            "m1_yoy": {"signal": "⚠️"}, "breadth": {"available": False}}},
        "tracks": [{"track_name": "AI算力", "position_ceiling": "进攻档", "available": True}],
        "indices": [{"name": "上证指数", "symbol": "sh000001", "price": 3500.0, "change_pct": 0.8}],
        "stocks": [
            {"group": "holding", "code": "002475", "configured_name": "立讯精密",
             "concepts": ["消费电子"], "realtime": {"name": "立讯精密", "price": 35.0},
             "metrics": {"right_side_score": 3.5, "ma5": 34.0, "rsi_14": 60}},
            {"group": "holding", "code": "600519", "configured_name": "贵州茅台",
             "concepts": [], "realtime": {"name": "贵州茅台", "price": 1700.0},
             "metrics": {"right_side_score": 2.0}},
            {"group": "watchlist", "code": "000858", "configured_name": "五粮液",
             "concepts": [], "realtime": {"name": "五粮液", "price": 150.0},
             "metrics": {"right_side_score": 1.2}},
            {"group": "watchlist", "code": "601318", "configured_name": "中国平安",
             "concepts": [], "realtime": {"name": "中国平安", "price": 50.0},
             "metrics": {"right_side_score": 0.3}},
            {"group": "watchlist", "code": "000333", "configured_name": "美的集团",
             "concepts": [], "realtime": {"name": "美的集团", "price": 60.0},
             "metrics": {"right_side_score": 2.8}},
        ],
    }


_PRICES = {"002475": 35.0, "600519": 1700.0, "000858": 150.0, "601318": 50.0, "000333": 60.0}


def _make_kline_stub(n_days):
    """构造 get_daily_kline 替身: 从 20260625 起 n_days 个序列日, close=base*(1+0.01*i)。"""
    base_date = dt.date(2026, 6, 25)
    seq = [(base_date + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(n_days)]

    def _kline(code, days=250):
        base = _PRICES.get(code, 100.0)
        return [{"trade_date": seq[i], "close": round(base * (1 + 0.01 * i), 6)} for i in range(n_days)]

    bench = {seq[i]: round(3000.0 * (1 + 0.005 * i), 6) for i in range(n_days)}
    return _kline, bench, seq


# ── 1. record_snapshots: 全 watchlist 每票一条, 锚 trade_date, filled=false, 带市场状态 ──
def test_record_snapshots_all_watchlist():
    d = tempfile.mkdtemp(prefix="vaxeval_")
    saved = _set_tmp(d)
    try:
        n = er.record_snapshots(_payload())
        rows = er._read_jsonl(er.SNAPSHOTS_FILE)
        assert n == 5 and len(rows) == 5
        for r in rows:
            assert r["trade_date"] == "20260625"      # 锚 payload, 非 now
            assert r["filled"] is False
            assert r["ret"] == {} and r["filled_ts"] is None
            assert r["metrics"]                        # 全量因子非空
            assert r["market"]["regime"] == "momentum"
            assert r["market"]["macro_regime"] == "🔴 看空"
            assert r["market"]["macro_signals"]["etf"] == "❌❌"
            assert r["market"]["macro_signals"]["breadth"] == "待"
            assert r["market"]["ai_track"]["position_ceiling"] == "进攻档"
            assert "上证指数" in r["market"]["index_snapshot"]
        groups = [r["group"] for r in rows]
        assert groups.count("holding") == 2 and groups.count("watchlist") == 3  # 全记
        by = {r["code"]: r for r in rows}
        assert by["002475"]["price_at_snapshot"] == 35.0   # 基准锚价
        assert by["002475"]["name"] == "立讯精密"
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


# ── 2. 幂等(同日不重复) + trade_date 缺失跳过 + warning ──
def test_record_snapshots_idempotent_and_missing_td():
    d = tempfile.mkdtemp(prefix="vaxeval_")
    saved = _set_tmp(d)
    records = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    h = _H()
    er.logger.addHandler(h)
    try:
        er.record_snapshots(_payload())
        n2 = er.record_snapshots(_payload())         # 再写同一 td -> 不重复
        assert n2 == 0
        assert len(er._read_jsonl(er.SNAPSHOTS_FILE)) == 5
        # trade_date 缺失 -> 跳过 + warning, 不写
        p = _payload()
        p["market_overview"] = {}
        n3 = er.record_snapshots(p)
        assert n3 == 0
        assert len(er._read_jsonl(er.SNAPSHOTS_FILE)) == 5
        assert any("跳过本次快照" in m for m in records), records
    finally:
        er.logger.removeHandler(h)
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


# ── 3. backfill: 真收盘机械算 ret/mkt_ret/excess; snapshots 不被改写(append-only) ──
def test_backfill_full_horizons_appendonly():
    d = tempfile.mkdtemp(prefix="vaxeval_")
    saved = _set_tmp(d)
    saved_bench = er._benchmark_closes
    try:
        er.record_snapshots(_payload())
        snap_text_before = er.SNAPSHOTS_FILE.read_text(encoding="utf-8")

        kline, bench, _ = _make_kline_stub(40)   # 充足天数(>=30)
        source = types.SimpleNamespace(get_daily_kline=kline)
        er._benchmark_closes = lambda src: bench

        n = er.backfill(source)
        res = er._read_jsonl(er.RESULTS_FILE)
        assert n == 5 and len(res) == 5
        r0 = next(x for x in res if x["code"] == "002475")
        assert set(r0["ret"].keys()) == {"1", "3", "5", "10", "20", "30"}
        # ret_k = 0.01*k(close 每日 +1%), mkt_k = 0.005*k(指数 +0.5%/日), excess = 差
        assert abs(r0["ret"]["5"] - 0.05) < 1e-6
        assert abs(r0["mkt_ret"]["5"] - 0.025) < 1e-6
        assert abs(r0["excess"]["5"] - 0.025) < 1e-6
        assert r0["complete"] is True
        # 关键: snapshots.jsonl 一字未改(append-only, 预测冻结)
        assert er.SNAPSHOTS_FILE.read_text(encoding="utf-8") == snap_text_before

        # 再 backfill: 已 complete -> 不重复 append
        n2 = er.backfill(source)
        assert n2 == 0
        assert len(er._read_jsonl(er.RESULTS_FILE)) == 5
    finally:
        er._benchmark_closes = saved_bench
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_backfill_partial_when_insufficient_days():
    d = tempfile.mkdtemp(prefix="vaxeval_")
    saved = _set_tmp(d)
    saved_bench = er._benchmark_closes
    try:
        er.record_snapshots(_payload())
        kline, bench, _ = _make_kline_stub(6)     # 仅 6 天: 1/3/5 可填, 10/20/30 不足
        source = types.SimpleNamespace(get_daily_kline=kline)
        er._benchmark_closes = lambda src: bench

        er.backfill(source)
        r0 = next(x for x in er._read_jsonl(er.RESULTS_FILE) if x["code"] == "002475")
        assert set(r0["ret"].keys()) == {"1", "3", "5"}   # 天数不足的 horizon 不填(不臆造)
        assert r0["complete"] is False
    finally:
        er._benchmark_closes = saved_bench
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_backfill_skips_when_index_missing():
    """指数取不到 -> ret 仍填, mkt_ret/excess 跳过(不臆造超额)。"""
    d = tempfile.mkdtemp(prefix="vaxeval_")
    saved = _set_tmp(d)
    saved_bench = er._benchmark_closes
    try:
        er.record_snapshots(_payload())
        kline, _, _ = _make_kline_stub(40)
        source = types.SimpleNamespace(get_daily_kline=kline)
        er._benchmark_closes = lambda src: {}      # 指数序列取不到

        er.backfill(source)
        r0 = next(x for x in er._read_jsonl(er.RESULTS_FILE) if x["code"] == "002475")
        assert set(r0["ret"].keys()) == {"1", "3", "5", "10", "20", "30"}
        assert r0["mkt_ret"] == {} and r0["excess"] == {}   # 指数缺 -> 不算超额
    finally:
        er._benchmark_closes = saved_bench
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


# ── 4. record_and_backfill: 先回填后记录 ──
def test_record_and_backfill_order():
    saved_bf, saved_rec = er.backfill, er.record_snapshots
    calls = []
    try:
        er.backfill = lambda source, **k: calls.append("backfill") or 0
        er.record_snapshots = lambda payload: calls.append("record") or 0
        out = er.record_and_backfill(_payload(), object())
        assert calls == ["backfill", "record"]   # 先回填(补历史)后记录(记当日)
        assert out == {"backfilled": 0, "snapshots": 0}
    finally:
        er.backfill, er.record_snapshots = saved_bf, saved_rec


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
