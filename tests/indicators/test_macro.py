# -*- coding: utf-8 -*-
"""indicators.macro 测试(MR-Macro B1+2)。

纯函数(grade/combine)+ MacroCache + 维度装配 + summary 占位 + akshare 墙钟超时 + 依赖守卫(ast)。
依赖守卫不 import macro(无需 pandas), 始终跑; 其余需 pandas/numpy/pyarrow, 缺则跳过(本容器),
VPS venv 实跑。全程零网络(monkeypatch source._safe_call / 注入 fake akshare)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/indicators/test_macro.py -q
     PYTHONPATH=src python3 tests/indicators/test_macro.py   # 无 pytest
"""

import ast
import importlib.util
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_MACRO_PY = _REPO / "src" / "vaxstock" / "indicators" / "macro.py"
_HAS_PANDAS = (importlib.util.find_spec("pandas") is not None
               and importlib.util.find_spec("numpy") is not None
               and importlib.util.find_spec("pyarrow") is not None)


class _SkipTest(Exception):
    """无 pandas/numpy/pyarrow 时跳过(非失败)。"""


def _macro():
    if not _HAS_PANDAS:
        raise _SkipTest("无 pandas/numpy/pyarrow, 跳过(VPS venv 实跑)")
    import vaxstock.indicators.macro as macro
    return macro


class _FakeSource:
    """注入式 source 替身: _safe_call(func) 按 responses 返回构造 df / None / 抛异常。零网络。"""

    enabled = True
    pro = object()

    def __init__(self, responses):
        self._responses = responses  # {func_name: df | None | callable(**kwargs)}
        self.calls = []

    def _safe_call(self, func_name, **kwargs):
        self.calls.append((func_name, dict(kwargs)))
        r = self._responses.get(func_name)
        if callable(r):
            return r(**kwargs)
        return r


# ════════ 1. grade_signal / combine_signals 纯函数(表驱动) ════════

def test_grade_signal_higher_better_buckets():
    macro = _macro()
    import numpy as np
    th = macro.SIGNAL_THRESHOLDS["etf_net_sub_5d"]  # bs30 b10 br-10 brs-30
    assert macro.grade_signal(35, th) == "✅✅"
    assert macro.grade_signal(15, th) == "✅"
    assert macro.grade_signal(0, th) == "⚠️"
    assert macro.grade_signal(-15, th) == "❌"
    assert macro.grade_signal(-35, th) == "❌❌"
    assert macro.grade_signal(None, th) == "🚫"
    assert macro.grade_signal(float(np.nan), th) == "🚫"


def test_grade_signal_lower_better_buckets():
    macro = _macro()
    th = macro.SIGNAL_THRESHOLDS["margin_ratio_pct_3y"]  # b30 br80 brs95 (无 bs)
    assert macro.grade_signal(20, th, direction="lower_better") == "✅"
    assert macro.grade_signal(50, th, direction="lower_better") == "⚠️"
    assert macro.grade_signal(85, th, direction="lower_better") == "❌"
    assert macro.grade_signal(96, th, direction="lower_better") == "❌❌"
    assert macro.grade_signal(None, th, direction="lower_better") == "🚫"


def test_combine_signals_regimes():
    macro = _macro()
    assert macro.combine_signals(["✅", "✅", "✅", "✅"]) == "🟢 强看多"
    assert macro.combine_signals(["✅✅", "✅✅"]) == "🟢 强看多"   # ✅✅×2 -> bull4
    assert macro.combine_signals(["✅", "✅", "✅"]) == "🟢 看多"
    assert macro.combine_signals(["❌", "❌", "❌", "❌"]) == "🔴 强看空"
    assert macro.combine_signals(["❌", "❌", "❌"]) == "🔴 看空"
    assert macro.combine_signals(["✅", "✅", "✅", "❌", "❌", "❌"]) == "🟡 中性"
    assert macro.combine_signals([]) == "🟡 中性"


# ════════ 2. MacroCache: parquet 往返 + 增量去重 + last_date ════════

def test_macro_cache_roundtrip_and_append():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        c = macro.MacroCache(d)
        assert c.load("nope") is None  # 不存在 -> None
        df = pd.DataFrame({"trade_date": ["20260101", "20260102"], "v": [1.0, 2.0]})
        assert c.save("t", df) is True
        back = c.load("t")
        assert list(back["trade_date"]) == ["20260101", "20260102"]
        assert list(back["v"]) == [1.0, 2.0]
        # 增量: 20260102 覆盖(keep last), 新增 20260103
        df2 = pd.DataFrame({"trade_date": ["20260102", "20260103"], "v": [9.0, 3.0]})
        merged = c.append_unique("t", df2, dedup_keys=["trade_date"])
        m = dict(zip(merged["trade_date"], merged["v"]))
        assert len(merged) == 3
        assert m["20260102"] == 9.0 and m["20260103"] == 3.0
        assert c.last_date("t") == "20260103"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ════════ 3. 维度方法装配(monkeypatch source._safe_call / akshare yield) ════════

def test_fetch_hs300_erp_akshare_math():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        pe = pd.DataFrame({"trade_date": ["20260101", "20260102"], "pe_ttm": [10.0, 20.0]})
        mi = macro.MacroIndicator(_FakeSource({"index_dailybasic": pe}), cache_dir=d)
        mi._fetch_cn_10y_yield_akshare = lambda: pd.DataFrame(
            {"trade_date": ["20260101", "20260102"], "yield_10y_pct": [2.5, 2.5]})
        out = mi.fetch_hs300_erp().sort_values("trade_date").reset_index(drop=True)
        # ERP = 1/PE*100 - yield: pe10->10-2.5=7.5 ; pe20->5-2.5=2.5
        assert abs(out.iloc[0]["erp_pct"] - 7.5) < 1e-9
        assert abs(out.iloc[1]["erp_pct"] - 2.5) < 1e-9
        assert set(out["yield_source"]) == {"akshare"}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_fetch_hs300_erp_fallback_yield():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        pe = pd.DataFrame({"trade_date": ["20260101"], "pe_ttm": [10.0]})
        mi = macro.MacroIndicator(_FakeSource({"index_dailybasic": pe}), cache_dir=d,
                                  fallback_yield_10y_pct=2.0)
        mi._fetch_cn_10y_yield_akshare = lambda: None  # akshare 不可用 -> fallback 常数
        out = mi.fetch_hs300_erp(fallback_yield_10y_pct=2.0)
        assert set(out["yield_source"]) == {"fallback"}
        assert abs(out.iloc[0]["yield_10y_pct"] - 2.0) < 1e-9
        assert abs(out.iloc[0]["erp_pct"] - 8.0) < 1e-9  # 1/10*100 - 2.0 = 8.0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_fetch_m1_yoy_structure():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        cn_m = pd.DataFrame({"month": ["202601", "202602", "202603"],
                             "m1": [100.0, 101.0, 102.0],
                             "m1_yoy": [5.0, 6.0, 5.5]})
        mi = macro.MacroIndicator(_FakeSource({"cn_m": cn_m}), cache_dir=d)
        out = mi.fetch_m1_yoy().sort_values("month").reset_index(drop=True)
        for col in ("month", "m1", "m1_yoy", "m1_yoy_mom_delta"):
            assert col in out.columns
        # mom_delta = m1_yoy.diff(): NaN, +1.0, -0.5
        assert pd.isna(out.iloc[0]["m1_yoy_mom_delta"])
        assert abs(out.iloc[1]["m1_yoy_mom_delta"] - 1.0) < 1e-9
        assert abs(out.iloc[2]["m1_yoy_mom_delta"] - (-0.5)) < 1e-9
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_fetch_etf_net_sub_structure():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        def share(ts_code=None, **k):
            if ts_code == "510300.SH":
                return pd.DataFrame({"trade_date": ["20260101", "20260102"], "fd_share": [1000.0, 1200.0]})
            return None  # 其余 4 只无数据 -> 跳过

        def daily(ts_code=None, **k):
            if ts_code == "510300.SH":
                return pd.DataFrame({"trade_date": ["20260101", "20260102"], "close": [4.0, 5.0]})
            return None

        mi = macro.MacroIndicator(_FakeSource({"fund_share": share, "fund_daily": daily}), cache_dir=d)
        out = mi.fetch_etf_net_subscription()
        out = out[out["etf_code"] == "510300.SH"].sort_values("trade_date").reset_index(drop=True)
        assert pd.isna(out.iloc[0]["share_change"])
        # 净申赎 = Δ份额(万份) × close(元) / 10000 = (1200-1000)*5/10000 = 0.1 亿
        assert abs(out.iloc[1]["net_sub_yi"] - 0.1) < 1e-9
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ════════ 4. summary: 维度5占位 + 已迁维度产出 + 单维失败隔离 ════════

def test_summary_breadth_placeholder_and_dim_isolation():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        cn_m = pd.DataFrame({"month": ["202601", "202602"], "m1": [1.0, 2.0], "m1_yoy": [9.0, 9.5]})

        def boom(**k):
            raise RuntimeError("注入故障")

        # m1 有数据 -> 产出信号; etf 的 fund_share 抛异常 -> 该维进 errors; 其余维 None -> 各自 errors
        mi = macro.MacroIndicator(_FakeSource({"cn_m": cn_m, "fund_share": boom}), cache_dir=d)
        res = mi.summary()

        # 维度5(B3)已迁: 无 index_daily/daily 数据 -> breadth available=False(不再是占位), 且进 errors
        assert res["indicators"]["breadth"]["available"] is False
        assert "pending" not in res["indicators"]["breadth"]   # 占位已删
        assert any(e.startswith("market_breadth_ma") for e in res["errors"])
        assert any(e.startswith("ma250_bias") for e in res["errors"])
        # 已迁维度6 有产出与信号
        assert "m1_yoy" in res["indicators"]
        assert len(res["signals"]) >= 1
        # 单维失败被隔离: etf 进 errors, summary 不抛
        assert any(e.startswith("etf_net_sub") for e in res["errors"])
        # 结构完整
        for k in ("timestamp", "indicators", "signals", "macro_regime", "errors"):
            assert k in res
        assert isinstance(res["macro_regime"], str)
        # 社融维度7 本 PR 不组装
        assert "sf_pulse" not in res["indicators"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ════════ 5. AkShare 国债收益率墙钟超时(注入 fake akshare, 不连网不真睡满) ════════

def test_akshare_yield_wallclock_timeout():
    macro = _macro()
    import shutil
    import sys
    import tempfile
    import time as _t
    import types as _types
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    saved_to = macro.AK_YIELD_TIMEOUT
    saved_mod = sys.modules.get("akshare")
    try:
        macro.AK_YIELD_TIMEOUT = 1  # 压低超时, 测试快速返回
        fake = _types.ModuleType("akshare")

        def _slow():
            _t.sleep(5)   # 超过 AK_YIELD_TIMEOUT, 模拟连接挂死
            return None

        fake.bond_zh_us_rate = _slow
        sys.modules["akshare"] = fake

        mi = macro.MacroIndicator(_FakeSource({}), cache_dir=d)
        t0 = _t.time()
        out = mi._fetch_cn_10y_yield_akshare()
        elapsed = _t.time() - t0
        assert out is None                 # 超时 -> None(不阻塞, 上层走 fallback)
        assert elapsed < 3                 # 墙钟超时 ~1s, 远小于 stub 的 5s
    finally:
        macro.AK_YIELD_TIMEOUT = saved_to
        if saved_mod is not None:
            sys.modules["akshare"] = saved_mod
        else:
            sys.modules.pop("akshare", None)
        shutil.rmtree(d, ignore_errors=True)


# ════════ 6. 依赖守卫(ast): 顶层不 import akshare(懒导入); 不 import 东财/monolith ════════

def test_macro_no_toplevel_akshare_no_forbidden():
    src = _MACRO_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    toplevel = []
    for node in tree.body:  # 仅模块级语句
        if isinstance(node, ast.Import):
            toplevel.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            toplevel.append(node.module or "")
            toplevel.extend(a.name for a in node.names)
    assert not any("akshare" in t for t in toplevel), \
        f"akshare 必须懒导入(方法内), 不得顶层 import: {toplevel}"

    alltokens = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            alltokens.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            alltokens.append(node.module or "")
            alltokens.extend(a.name for a in node.names)
    forbidden = ["eastmoney", "stock_report_enhanced", "opportunity_scanner",
                 "hot_sector_scanner"]
    offenders = [t for t in alltokens if any(fb in t for fb in forbidden)]
    assert offenders == [], f"macro.py 不应 import 东财/monolith: {offenders}"


# ════════ 7. 维度5 全市场宽度(B3): 纯计算 / 增量 / 未结算守卫 / BIAS / 过滤 / summary 切真值 ════════

def _dates(n, start=(2026, 1, 5)):
    import datetime as _dt
    base = _dt.date(*start)
    return [(base + _dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


def test_compute_breadth_from_klines_math():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        dates = _dates(45)   # 45 日: MA60(min_periods40)有效, MA200(min_periods120)不足
        rows = []
        for i, td in enumerate(dates):
            rows.append({"trade_date": td, "ts_code": "000001.SZ", "close": 10 + i * 0.1})   # 上升
            rows.append({"trade_date": td, "ts_code": "000002.SZ", "close": 20 - i * 0.1})   # 下降
            rows.append({"trade_date": td, "ts_code": "600000.SH", "close": 30.0})           # 平
        kc = pd.DataFrame(rows)
        mi = macro.MacroIndicator(_FakeSource({}), cache_dir=d)
        out = mi._compute_breadth_from_klines(kc, "market_breadth_ratio_history") \
                .sort_values("trade_date").reset_index(drop=True)
        last = out.iloc[-1]
        assert int(last["valid_count_ma60"]) == 3           # 3 票 MA60 均有效
        assert abs(last["above_ma60_pct"] - 100.0 / 3) < 1e-6  # 仅上升票在 MA60 之上
        assert int(last["valid_count_ma200"]) == 0          # 45<120 -> MA200 无效
        assert pd.isna(last["above_ma200_pct"])             # 无有效票 -> NaN(不臆造)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _daily_rows(td, n=1005, prefix="6001"):
    return [{"trade_date": td, "ts_code": f"{prefix}{i:04d}.SH", "close": 10.0 + i} for i in range(n)]


def test_breadth_incremental_append_and_dedup():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        def _idx(ts_code=None, **k):
            return pd.DataFrame({"trade_date": ["20260105", "20260106"]}) if ts_code == "000001.SH" else None

        def _daily(trade_date=None, **k):
            return pd.DataFrame(_daily_rows("20260106")) if trade_date == "20260106" else None

        mi = macro.MacroIndicator(_FakeSource({"index_daily": _idx, "daily": _daily}), cache_dir=d)
        # 预置 day1 pivot(5 行)
        day1 = pd.DataFrame([{"trade_date": "20260105", "ts_code": f"6000{i:02d}.SH", "close": 10.0 + i}
                             for i in range(5)])
        mi.cache.save("stocks_daily_pivot", day1)

        mi._fetch_breadth_ma_ratio()
        pivot = mi.cache.load("stocks_daily_pivot")
        assert str(pivot["trade_date"].max()) == "20260106"          # kline_last 推进
        assert len(pivot) == 5 + 1005                                # day1 + day2 全留
        assert pivot.duplicated(subset=["ts_code", "trade_date"]).sum() == 0   # 无重复
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_breadth_unsettled_guard_skips():
    macro = _macro()
    import logging
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    records = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    h = _H()
    macro.logger.addHandler(h)
    try:
        def _idx(ts_code=None, **k):
            return pd.DataFrame({"trade_date": ["20260105", "20260106"]}) if ts_code == "000001.SH" else None

        def _daily(trade_date=None, **k):
            # 20260106 仅 50 行(< MIN_DAILY_ROWS) -> 视为未结算, 跳过
            return pd.DataFrame(_daily_rows("20260106", n=50)) if trade_date == "20260106" else None

        mi = macro.MacroIndicator(_FakeSource({"index_daily": _idx, "daily": _daily}), cache_dir=d)
        day1 = pd.DataFrame([{"trade_date": "20260105", "ts_code": f"6000{i:02d}.SH", "close": 10.0 + i}
                             for i in range(5)])
        mi.cache.save("stocks_daily_pivot", day1)

        mi._fetch_breadth_ma_ratio()
        pivot = mi.cache.load("stocks_daily_pivot")
        assert "20260106" not in set(pivot["trade_date"].astype(str))   # 未结算日不进 pivot
        assert str(pivot["trade_date"].max()) == "20260105"
        assert any("疑未结算" in m for m in records), records
    finally:
        macro.logger.removeHandler(h)
        shutil.rmtree(d, ignore_errors=True)


def test_fetch_ma250_bias_math():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        dates = _dates(210)                       # 210 日: MA250(min_periods200)末行有效, 早期无效
        closes = [100.0 + i * 0.5 for i in range(210)]

        def _idx(ts_code=None, **k):
            return pd.DataFrame({"trade_date": dates, "close": closes}) if ts_code == macro.WHOLE_MARKET_PROXY else None

        mi = macro.MacroIndicator(_FakeSource({"index_daily": _idx}), cache_dir=d)
        out = mi._fetch_ma250_bias().sort_values("trade_date").reset_index(drop=True)
        last = out.iloc[-1]
        # 末行 MA250 = 全 210 日均值(窗口 250 但仅 210 可用, min_periods200 满足)
        exp_ma = sum(closes) / len(closes)
        exp_bias = (closes[-1] - exp_ma) / exp_ma * 100
        assert abs(last["bias_pct"] - exp_bias) < 1e-6
        assert pd.isna(last["percentile_5y"])     # 半窗(625)不足 -> NaN
        assert pd.isna(out.iloc[0]["bias_pct"])   # 前期 MA250 不足 -> NaN
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_breadth_filters_bse_and_star():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        def _idx(ts_code=None, **k):
            return pd.DataFrame({"trade_date": ["20260106"]}) if ts_code == "000001.SH" else None

        def _daily(trade_date=None, **k):
            rows = _daily_rows("20260106", n=1000)              # 主板/创业板代理
            rows += [{"trade_date": "20260106", "ts_code": "830001.BJ", "close": 5.0},   # 北交所 8 字头
                     {"trade_date": "20260106", "ts_code": "688001.SH", "close": 50.0}]  # 科创 688
            return pd.DataFrame(rows)

        mi = macro.MacroIndicator(_FakeSource({"index_daily": _idx, "daily": _daily}), cache_dir=d)
        mi._fetch_breadth_ma_ratio()
        codes = set(mi.cache.load("stocks_daily_pivot")["ts_code"].astype(str))
        assert "830001.BJ" not in codes and "688001.SH" not in codes   # 8/688 被滤除
        assert len(codes) == 1000
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_summary_dim5_live_and_isolation():
    macro = _macro()
    import shutil
    import tempfile

    import pandas as pd
    d = tempfile.mkdtemp(prefix="vaxmacro_")
    try:
        breadth_df = pd.DataFrame({
            "trade_date": ["20260105", "20260106"],
            "above_ma60_pct": [80.0, 78.0], "above_ma200_pct": [70.0, 68.0],
            "above_ma60_percentile_5y": [90.0, 88.0], "above_ma200_percentile_5y": [85.0, 83.0],
            "valid_count_ma60": [4000, 4010], "valid_count_ma200": [3900, 3950]})
        bias_df = pd.DataFrame({"trade_date": ["20260105", "20260106"],
                                "bias_pct": [5.0, 6.0], "percentile_5y": [80.0, 82.0]})
        mi = macro.MacroIndicator(_FakeSource({}), cache_dir=d)
        mi.fetch_market_breadth = lambda: {"breadth": breadth_df, "bias": bias_df}
        res = mi.summary()
        b = res["indicators"]["breadth"]
        assert b["available"] is True
        assert b["above_ma60_pct"] == 78.0 and b["above_ma200_pct"] == 68.0 and b["ma250_bias_pct"] == 6.0
        # lower_better: above_ma60 78≥75 -> ❌; above_ma200 68≥65 -> ❌; bias 6≥3 -> ❌
        assert b["above_ma60_signal"] == "❌" and b["above_ma200_signal"] == "❌" and b["ma250_bias_signal"] == "❌"
        assert res["signals"].count("❌") >= 3              # 三宽度信号进 signals
        assert isinstance(res["macro_regime"], str)        # combine 自然纳入维度5

        # 异常隔离: fetch_market_breadth 抛 -> 进 errors, breadth available False, summary 不崩
        mi2 = macro.MacroIndicator(_FakeSource({}), cache_dir=d)

        def _boom():
            raise RuntimeError("注入故障")

        mi2.fetch_market_breadth = _boom
        res2 = mi2.summary()
        assert res2["indicators"]["breadth"]["available"] is False
        assert any(e.startswith("market_breadth:") for e in res2["errors"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    skipped = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except _SkipTest as e:
            skipped += 1
            print(f"  [SKIP] {name}: {e}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed-skipped}/{len(fns)} passed, {skipped} skipped")
    sys.exit(1 if failed else 0)
