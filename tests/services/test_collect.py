# -*- coding: utf-8 -*-
"""services.collect 测试: 依赖守卫(ast 静态) + 装配纯逻辑(stub source, 零网络)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/services/test_collect.py -q
     PYTHONPATH=src python3 tests/services/test_collect.py   # 无 pytest
"""

import ast
import datetime as dt
import pathlib

from vaxstock import config
from vaxstock.services import collect as collect_mod
from vaxstock.services.collect import collect_payload
from vaxstock.tracks import contract

_REPO = pathlib.Path(__file__).resolve().parents[2]


# ── 依赖守卫1: collect.py 不得 import 东财/未迁模块(ast 静态, 不用运行时 sys.modules) ──
def test_collect_no_forbidden_imports():
    src = (_REPO / "src" / "vaxstock" / "services" / "collect.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    tokens = []  # 所有 import 模块名 + from-import 的符号名
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            tokens.append(node.module or "")
            tokens.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            tokens.extend(a.name for a in node.names)
    forbidden = ["eastmoney", "opportunity_scanner", "hot_sector_scanner",
                 "macro_indicators", "build_sector_analysis"]
    offenders = [t for t in tokens if any(fb in t for fb in forbidden)]
    assert offenders == [], f"collect.py 不应 import 东财/未迁模块: {offenders}"


# ── 依赖守卫2: 新包 src/vaxstock 内 _CURRENT_MARKET_REGIME 不作为代码标识符出现 ──
# 用 ast 走 Name/Global(自然排除 docstring/注释), 比裸 grep 准: stock_item.py 文档里提到该名是
# 在说明"已移除", 属文档不属活代码; KPI 是"全局作为代码=0"。
def test_no_current_market_regime_global():
    offenders = []
    for py in sorted((_REPO / "src" / "vaxstock").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Global) and "_CURRENT_MARKET_REGIME" in node.names:
                offenders.append(f"{py.name}: global")
            if isinstance(node, ast.Name) and node.id == "_CURRENT_MARKET_REGIME":
                offenders.append(f"{py.name}: Name")
    assert offenders == [], f"新包不应再有 _CURRENT_MARKET_REGIME 活代码: {offenders}"


# ── 装配纯逻辑测: stub source 喂 canned indices/overview/hsgt, 全程零网络 ──
class _StubSource:
    points_level = 2000
    enabled = True

    def get_index_daily(self, code):
        return {"ts_code": code, "trade_date": "20260625", "close": 3500.0,
                "pct_chg": -1.0, "vol": 1.0, "amount": 1.0}

    def get_market_daily(self, trade_date, fields="ts_code,pct_chg"):
        # 60 只主板跌停(<=-9.8) -> limit_down_count=60 -> regime 必为 panic(确定性)
        rows = [{"ts_code": f"6000{i:02d}.SH", "pct_chg": -9.9} for i in range(60)]
        rows.append({"ts_code": "600999.SH", "pct_chg": 3.0})
        return rows

    def get_hsgt_flow(self, days=10):
        # 单位万元: 120000万=12亿
        return [{"trade_date": "20260625", "north_money": 120000.0,
                 "hgt": 70000.0, "sgt": 50000.0}]


class _StubAITrack:
    def __init__(self, source=None):
        self.source = source

    def evaluate(self):
        return contract.pending_result("AI算力", str(dt.date.today()),
                                       "单测 stub, 不连网", pending_dims=["stub维度"])


def _run_collect_with_stubs():
    """monkeypatch 掉所有触网 seam, 用 stub source 跑 collect_payload。返回 (payload, tracks)。"""
    saved = {
        "load_watchlist": config.load_watchlist,
        "load_holdings": config.load_holdings,
        "fetch_us": collect_mod.fetch_us_market_data,
        "AITrack": collect_mod.AITrack,
        "sleep": collect_mod.time.sleep,
    }
    try:
        config.load_watchlist = lambda: ({}, {})   # 空池 -> 不调 build_stock_item(避免 sina 连网)
        config.load_holdings = lambda: {}
        collect_mod.fetch_us_market_data = lambda: {"sentiment": "stub", "indices": []}
        collect_mod.AITrack = _StubAITrack
        collect_mod.time.sleep = lambda *_a, **_k: None
        return collect_payload(_StubSource())
    finally:
        config.load_watchlist = saved["load_watchlist"]
        config.load_holdings = saved["load_holdings"]
        collect_mod.fetch_us_market_data = saved["fetch_us"]
        collect_mod.AITrack = saved["AITrack"]
        collect_mod.time.sleep = saved["sleep"]


def test_collect_payload_assembly():
    payload, tracks = _run_collect_with_stubs()

    # 骨架字段齐全
    for k in ["generated_at", "data_sources", "tushare_points_level", "indices",
              "stocks", "market_overview", "north_flow", "hsgt_flow_history", "market_regime"]:
        assert k in payload, f"缺骨架字段: {k}"

    # data_sources 只留 sina + tushare, 无 eastmoney
    assert "sina_realtime" in payload["data_sources"]
    assert "tushare_pro_lv2000" in payload["data_sources"]
    assert not any("eastmoney" in d for d in payload["data_sources"])

    # market_regime == 注入数据(60跌停)推出的值 = panic
    assert payload["market_overview"].get("limit_down_count") == 60
    assert payload["market_regime"] == "panic", payload["market_regime"]

    # 指数装配自 stub(5 个 INDEX_LIST 标的)
    assert len(payload["indices"]) == len(config.INDEX_LIST)

    # 北向资金装配(stub 12亿)
    assert payload["north_flow"]["total_inflow"] == 12.0

    # 东财砍除三段诚实降级 available=False
    for seg in ["sector_analysis", "hot_sector_scan", "opportunity_scan"]:
        assert payload[seg]["available"] is False, seg

    # tracks 序列化为 dict 列表(可 replay), 且是合规 TrackResult
    assert isinstance(payload["tracks"], list) and len(payload["tracks"]) == 1
    assert isinstance(payload["tracks"][0], dict)
    assert contract.validate(payload["tracks"][0]) == []
    # 返回的 track_results 与序列化版一致
    assert len(tracks) == 1 and tracks[0]["track_name"] == "AI算力"


def test_collect_payload_no_crash_minimal():
    """空池 + stub 不抛异常即视为串联完整。"""
    payload, tracks = _run_collect_with_stubs()
    assert isinstance(payload, dict) and isinstance(tracks, list)
    assert payload["stocks"] == []  # 空池下无个股


# ── 交易日锚定(PR-TZ): 北向 is_today 对照市场交易日, 凌晨 T+1 跑 T 日北向仍标 is_today ──
def test_north_flow_is_today_anchors_to_trade_date():
    """now=凌晨 T+1(2026-06-26), 市场交易日与 hsgt 行均为 T(20260625) -> is_today 仍 True。
    (旧 now() 口径会判 False; 本测试守住锚交易日修复。)"""
    saved_datetime = collect_mod.datetime
    try:
        class _FixedNow:
            @staticmethod
            def now():
                return dt.datetime(2026, 6, 26, 5, 0, 0)  # 凌晨 T+1

        collect_mod.datetime = _FixedNow
        payload, _ = _run_collect_with_stubs()
        nf = payload["north_flow"]
        assert nf["trade_date"] == "20260625"          # stub 市场交易日 T
        assert nf["is_today"] is True, nf               # 锚交易日 -> T 日北向仍算今日
        assert nf["note"] is None                       # is_today True -> 无滞后标注
    finally:
        collect_mod.datetime = saved_datetime


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
