# -*- coding: utf-8 -*-
"""AI 赛道 _assemble 纯函数测试(零网络)。

只测 ai._assemble: 用 mock 信号 dict 驱动, 不触网络、不需要 akshare/pandas/numpy。
每个用例都断言 contract.validate(result) == []。

跑法:
  PYTHONPATH=src python3 -m pytest tests/tracks/test_ai.py
  PYTHONPATH=src python3 tests/tracks/test_ai.py      # 无 pytest 时
"""

import importlib.util

import vaxstock.tracks.ai as ai_mod
from vaxstock.tracks import contract
from vaxstock.tracks.ai import AITrack, _assemble

DATE = "2026-06-25"

# 注意: 不在模块顶层 import pandas(否则会让 test_assemble_pure_no_heavy_deps 误判 pandas 泄漏)。
# 用 find_spec 仅探测可用性、不加载。pandas 缺失(本容器)-> 三条 status 路径测跳过, VPS venv 实跑。
_HAS_PANDAS = importlib.util.find_spec("pandas") is not None


class _SkipTest(Exception):
    """无 pandas 等前置依赖时跳过(非失败)。"""


def _good_signals():
    """四信号全好: 景气✅扩张加速 + 闸门开 + 情绪平稳 + 不拥挤。"""
    return {
        "prosperity": {"signal": "✅扩张加速", "status": "已证实", "yoy_pct": 55.0,
                       "qoq_pct": 12.0, "accel_pp": 2.0, "latest_rev_busd": 350.0,
                       "cross_validated": True},
        "sox_gate": {"gate_open": True, "status": "已证实", "sox_close": 5200.0,
                     "sox_ma50": 5000.0, "above_ma50": True, "mom_1m_pct": 4.0,
                     "trigger": []},
        "qvix": {"status": "已证实", "mood": "✅情绪平稳", "qvix_300": 18.0, "qvix_cyb": 28.0},
        "crowding": {"status": "已证实", "turnover_pctile": 0.55, "basket_52w_pos": 0.60,
                     "missing": []},
    }


def _veto_names(r):
    return [v[0] for v in r["vetoes"]]


# ① 四信号全好 -> available=True、进攻档前缀、validate()==[]
def test_all_good_offense():
    r = _assemble(_good_signals(), DATE)
    assert r["available"] is True
    assert r["position_ceiling"].startswith(contract.CEILING_OFFENSE), r["position_ceiling"]
    assert r["track_name"] == "AI算力"
    assert r["date"] == DATE
    assert r["vetoes"] == []
    assert len(r["summary_lines"]) >= 4
    assert contract.validate(r) == [], contract.validate(r)


# ② 闸门关闭 -> "海外闸门" veto、降档、validate()==[]
def test_gate_closed_veto_downgrade():
    s = _good_signals()
    s["sox_gate"] = {"gate_open": False, "status": "已证实", "sox_close": 4800.0,
                     "sox_ma50": 5000.0, "above_ma50": False, "mom_1m_pct": -3.0,
                     "trigger": ["跌破MA50(5000)", "近1月动量转负(-3.0%)"]}
    r = _assemble(s, DATE)
    assert "海外闸门" in _veto_names(r), r["vetoes"]
    # 单否决 -> 减档(降档), 仍可出仓位结论
    assert r["position_ceiling"].startswith(contract.CEILING_REDUCE), r["position_ceiling"]
    assert r["available"] is True
    assert contract.validate(r) == [], contract.validate(r)


# ③ 拥挤度超阈 -> "拥挤度" veto、validate()==[]
def test_crowding_veto():
    s = _good_signals()
    s["crowding"]["turnover_pctile"] = 0.95  # > 0.90
    r = _assemble(s, DATE)
    assert "拥挤度" in _veto_names(r), r["vetoes"]
    assert contract.validate(r) == [], contract.validate(r)

    # 另一触发路径: 篮子52周位置 > 0.90
    s2 = _good_signals()
    s2["crowding"]["basket_52w_pos"] = 0.93
    r2 = _assemble(s2, DATE)
    assert "拥挤度" in _veto_names(r2), r2["vetoes"]
    assert contract.validate(r2) == [], contract.validate(r2)


# ④ 景气证伪 -> "景气证伪" veto、清仓档、validate()==[]
def test_prosperity_falsified_liquidate():
    s = _good_signals()
    s["prosperity"]["signal"] = "❌景气转负"
    r = _assemble(s, DATE)
    assert "景气证伪" in _veto_names(r), r["vetoes"]
    assert r["position_ceiling"].startswith(contract.CEILING_LIQUIDATE), r["position_ceiling"]
    assert r["available"] is True  # 清仓档仍是有效档位(非数据缺失)
    assert contract.validate(r) == [], contract.validate(r)


# ⑤ 关键信号缺失 -> available=False、档位=PENDING_CEILING、pending 非空、validate()==[]
def test_key_signal_missing_pending():
    s = _good_signals()
    s["prosperity"] = {"signal": None, "status": "待验证", "note": "NVDA营收获取失败(ak)"}
    s["sox_gate"] = {"gate_open": None, "status": "待验证", "note": "SOX获取失败"}
    r = _assemble(s, DATE)
    assert r["available"] is False
    assert r["position_ceiling"] == contract.PENDING_CEILING  # 精确相等
    assert len(r["pending"]) > 0
    assert contract.validate(r) == [], contract.validate(r)

    # 只缺景气 signal 也应 pending
    s2 = _good_signals()
    s2["prosperity"]["signal"] = None
    s2["prosperity"]["status"] = "待验证"
    r2 = _assemble(s2, DATE)
    assert r2["available"] is False
    assert r2["position_ceiling"] == contract.PENDING_CEILING
    assert len(r2["pending"]) > 0
    assert contract.validate(r2) == [], contract.validate(r2)


# 多重否决 -> 防御档(覆盖梯度另一支)
def test_multi_veto_defense():
    s = _good_signals()
    s["sox_gate"]["gate_open"] = False
    s["sox_gate"]["trigger"] = ["跌破MA50(5000)"]
    s["crowding"]["turnover_pctile"] = 0.96
    r = _assemble(s, DATE)
    assert len(r["vetoes"]) >= 2
    assert r["position_ceiling"].startswith(contract.CEILING_DEFENSE), r["position_ceiling"]
    assert contract.validate(r) == [], contract.validate(r)


# import 隔离回归守卫: 导入 ai 并跑 _assemble 全程不得加载 akshare/pandas/numpy/yfinance
def test_assemble_pure_no_heavy_deps():
    import sys
    _assemble(_good_signals(), DATE)
    leaked = [m for m in ("akshare", "pandas", "numpy", "yfinance") if m in sys.modules]
    assert leaked == [], f"_assemble 路径泄漏了重依赖: {leaked}"


# ── yfinance 交叉验证套墙钟超时(本 PR 核心): 直测 _yf_safe_latest_nvda_rev, 零网络 ──

def test_yf_safe_timeout_returns_none_fast():
    """注入会卡死的假 yfinance + 调小 YF_CALL_TIMEOUT -> 立即放弃返回 None, 不阻塞。"""
    import sys
    import time
    import types

    saved_to = ai_mod.YF_CALL_TIMEOUT
    saved_mod = sys.modules.get("yfinance")
    try:
        ai_mod.YF_CALL_TIMEOUT = 0.3
        fake = types.ModuleType("yfinance")

        def _slow_ticker(symbol):
            time.sleep(5)  # 远超 YF_CALL_TIMEOUT
            raise RuntimeError("不该执行到这里(应已超时放弃)")

        fake.Ticker = _slow_ticker
        sys.modules["yfinance"] = fake

        t0 = time.time()
        val = ai_mod._yf_safe_latest_nvda_rev()
        elapsed = time.time() - t0

        assert val is None, "超时应返回 None"
        assert elapsed < 2.0, f"join(0.3) 应立即放弃, 不等满 5s; 实测 {elapsed:.2f}s"
    finally:
        ai_mod.YF_CALL_TIMEOUT = saved_to
        if saved_mod is not None:
            sys.modules["yfinance"] = saved_mod
        else:
            sys.modules.pop("yfinance", None)


def test_yf_safe_error_returns_none():
    """假 yfinance 立即抛异常 -> _yf_safe 捕获返回 None(上层标单源, 不抛)。"""
    import sys
    import types

    saved_mod = sys.modules.get("yfinance")
    try:
        fake = types.ModuleType("yfinance")

        def _boom(symbol):
            raise ValueError("boom")

        fake.Ticker = _boom
        sys.modules["yfinance"] = fake
        assert ai_mod._yf_safe_latest_nvda_rev() is None
    finally:
        if saved_mod is not None:
            sys.modules["yfinance"] = saved_mod
        else:
            sys.modules.pop("yfinance", None)


# ── 三态 status 路径(需 pandas 构造 ak df; 缺 pandas 则跳过, VPS venv 实跑)──

_AK_DATES = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
             "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]


def _make_ak_rev_df(amounts):
    import pandas as pd
    rows = [{"STD_ITEM_CODE": "004001001", "REPORT_DATE": _AK_DATES[i], "AMOUNT": amt}
            for i, amt in enumerate(amounts)]
    return pd.DataFrame(rows)


def _prosperity_with(yf_val):
    """ak 数据正常(6季), _yf_safe 返回 yf_val(monkeypatch) -> 跑 fetch_nvda_prosperity。"""
    if not _HAS_PANDAS:
        raise _SkipTest("无 pandas, 跳过(VPS venv 实跑)")
    df = _make_ak_rev_df([100.0, 110.0, 120.0, 130.0, 140.0, 160.0])  # rev[-1]=160
    saved_ak = ai_mod._ak_safe
    saved_yf = ai_mod._yf_safe_latest_nvda_rev
    try:
        ai_mod._ak_safe = lambda *a, **k: df
        ai_mod._yf_safe_latest_nvda_rev = lambda: yf_val
        return AITrack().fetch_nvda_prosperity()
    finally:
        ai_mod._ak_safe = saved_ak
        ai_mod._yf_safe_latest_nvda_rev = saved_yf


def test_cross_single_source_when_yf_none():
    # yfinance 超时/不可用 -> cross_ok=None -> 单源待交叉验证, 但 signal 仍产出(不卡不抛)
    r = _prosperity_with(None)
    assert r["signal"] is not None
    assert r["status"] == "单源待交叉验证", r["status"]


def test_cross_confirmed_when_close():
    # 双源相差 <2% -> 已证实
    r = _prosperity_with(160.0 * 1.005)
    assert r["status"] == "已证实", r["status"]
    # cross_validated 源自 numpy 比较(rev[-1] 是 numpy.float64 -> numpy.bool_),
    # 不能用 is 做身份比较(numpy.bool_(True) is True -> False), 转成 Python bool 再比
    assert bool(r["cross_validated"]) is True


def test_cross_conflict_when_far():
    # 双源相差 >2% -> 双源冲突待验证
    r = _prosperity_with(160.0 * 1.5)
    assert r["status"] == "双源冲突待验证", r["status"]


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
