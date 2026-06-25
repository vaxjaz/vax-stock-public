# -*- coding: utf-8 -*-
"""regime 纯重放 + trade_date key 测试(IO 用临时文件重定向, 零网络)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/indicators/test_regime.py -q
     PYTHONPATH=src python3 tests/indicators/test_regime.py   # 无 pytest
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

from vaxstock import config
from vaxstock.indicators import regime as R
from vaxstock.indicators.regime import _replay, _transition, detect_market_regime


def _with_temp_state(fn):
    """把 config.REGIME_STATE_FILE 重定向到临时文件跑 fn(state_file_path), 用后清理。"""
    d = tempfile.mkdtemp(prefix="vaxregime_")
    saved = config.REGIME_STATE_FILE
    try:
        config.REGIME_STATE_FILE = Path(d) / "regime_history.json"
        return fn(config.REGIME_STATE_FILE)
    finally:
        config.REGIME_STATE_FILE = saved
        shutil.rmtree(d, ignore_errors=True)


def _read_raw_history(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("raw_history")


# ── 2. 转移规则表驱动(直接测纯函数)──
def test_transition_rules_table():
    # panic 单日立即
    assert _transition("momentum", ["panic"]) == "panic"
    assert _transition("value", ["value", "panic"]) == "panic"
    # panic 解除需连续2日非panic
    assert _transition("panic", ["panic", "momentum"]) == "panic"      # 未满2日非panic
    assert _transition("panic", ["momentum", "momentum"]) == "momentum"  # 连续2日非panic -> 解除
    assert _transition("panic", ["momentum"]) == "panic"               # 仅1日 -> 维持panic
    # m<->v 互切需连续2日同向
    assert _transition("momentum", ["momentum", "value"]) == "momentum"  # 单日v不切
    assert _transition("momentum", ["value", "value"]) == "value"        # 连续2日v -> 切
    assert _transition("momentum", ["value"]) == "momentum"              # 仅1日 -> 维持
    # 同向维持
    assert _transition("value", ["value", "value"]) == "value"


def test_replay_sequences():
    def H(*raws):
        return [{"trade_date": f"202601{i:02d}", "raw": r} for i, r in enumerate(raws, 1)]

    assert _replay(H("panic")) == "panic"
    assert _replay(H("panic", "momentum")) == "panic"                  # 未满2日解除
    assert _replay(H("panic", "momentum", "momentum")) == "momentum"   # 连续2日非panic解除
    assert _replay(H("momentum", "value", "momentum")) == "momentum"   # 插单日v维持m
    assert _replay(H("momentum", "value", "value")) == "value"         # 连续2日v切v
    assert _replay([]) == "momentum"                                   # 冷启动种子


# ── 1. 幂等: 同 trade_date 连跑5次, 返回值相同且 raw_history 不增不变 ──
def test_idempotent_same_trade_date():
    def body(path):
        ov = {"trade_date": "20260115", "limit_down_count": 60}  # raw=panic, 确定性
        rets = [detect_market_regime([], ov) for _ in range(5)]
        assert rets == ["panic"] * 5, rets
        rh = _read_raw_history(path)
        assert rh is not None and len(rh) == 1, rh           # 同日只 1 条
        assert rh[0]["trade_date"] == "20260115" and rh[0]["raw"] == "panic"
        # 再跑两次, raw_history 仍不变
        snapshot = json.dumps(rh, ensure_ascii=False)
        detect_market_regime([], ov)
        detect_market_regime([], ov)
        assert json.dumps(_read_raw_history(path), ensure_ascii=False) == snapshot
    _with_temp_state(body)


# ── 3. 非交易日不污染: 同 trade_date 复用(模拟周六复用周五)-> 长度不增、无新 date ──
def test_non_trading_day_no_pollution():
    def body(path):
        ov_fri = {"trade_date": "20260116", "limit_down_count": 0,
                  "up_count": 100}  # 指数空 -> raw=momentum
        detect_market_regime([], ov_fri)
        rh1 = _read_raw_history(path)
        # 周六/周日复用周五的 trade_date 再跑两次
        detect_market_regime([], ov_fri)
        detect_market_regime([], ov_fri)
        rh2 = _read_raw_history(path)
        assert len(rh1) == len(rh2) == 1
        assert {h["trade_date"] for h in rh2} == {"20260116"}  # 无新增幽灵日期
    _with_temp_state(body)


# ── 4. trade_date 缺失 -> 不写盘 + 仍返回合法 regime ──
def test_missing_trade_date_no_write():
    def body(path):
        # 4a: 全新(无文件), 传 {} -> 不创建文件
        assert not os.path.exists(path)
        r = detect_market_regime([], {})
        assert r in ("momentum", "value", "panic")
        assert not os.path.exists(path), "trade_date 缺失不应写盘(不应创建文件)"

        # 4b: 已有状态, 传无 trade_date -> 文件内容不变 + 返回历史重放
        detect_market_regime([], {"trade_date": "20260120", "limit_down_count": 60})
        before = Path(path).read_text(encoding="utf-8")
        r2 = detect_market_regime([], {})          # 无 trade_date
        assert r2 in ("momentum", "value", "panic")
        assert r2 == "panic"                        # 历史里是 panic, 重放仍 panic
        after = Path(path).read_text(encoding="utf-8")
        assert before == after, "trade_date 缺失不应改动已有状态文件"
    _with_temp_state(body)


# ── 多日演进 + 幂等组合: value 连续2日才切, 切后重放稳定 ──
def test_multiday_evolution_and_replay_stability():
    def body(path):
        val_ov = lambda td: {"trade_date": td, "limit_down_count": 0}
        val_idx = [{"name": "上证指数", "change_pct": 1.5}]  # sh跑赢 -> raw=value
        d1 = detect_market_regime(val_idx, val_ov("20260201"))  # 第1日 value -> 维持 momentum
        assert d1 == "momentum"
        d2 = detect_market_regime(val_idx, val_ov("20260202"))  # 连续2日 value -> 切 value
        assert d2 == "value"
        # 重跑第2日(幂等)
        assert detect_market_regime(val_idx, val_ov("20260202")) == "value"
        rh = _read_raw_history(path)
        assert [h["raw"] for h in rh] == ["value", "value"]
    _with_temp_state(body)


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
