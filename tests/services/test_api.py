# -*- coding: utf-8 -*-
"""services.api 测试: 依赖/消全局守卫(ast 静态) + TestClient 行为(零网络, monkeypatch seam)。

AST 守卫不 import api(无需 fastapi)。TestClient 测需 fastapi+httpx, 缺则跳过(本容器), VPS venv 实跑。
跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/services/test_api.py -q
     PYTHONPATH=src python3 tests/services/test_api.py   # 无 pytest
"""

import ast
import importlib.util
import os
import pathlib
import shutil
import tempfile

_REPO = pathlib.Path(__file__).resolve().parents[2]
_API_PY = _REPO / "src" / "vaxstock" / "services" / "api.py"
_HAS_FASTAPI = (importlib.util.find_spec("fastapi") is not None
                and importlib.util.find_spec("httpx") is not None)


class _SkipTest(Exception):
    """无 fastapi/httpx 时跳过(非失败)。"""


def _api_tokens():
    tree = ast.parse(_API_PY.read_text(encoding="utf-8"))
    tokens = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            tokens.append(node.module or "")
            tokens.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            tokens.extend(a.name for a in node.names)
    return tokens


# ── 1. 依赖守卫(ast 静态): 不 import monolith / 东财 / 未迁模块 ──
def test_api_no_forbidden_imports():
    forbidden = ["stock_report_enhanced", "eastmoney", "opportunity_scanner",
                 "hot_sector_scanner", "macro_indicators"]
    offenders = [t for t in _api_tokens() if any(fb in t for fb in forbidden)]
    assert offenders == [], f"api.py 不应 import monolith/东财/未迁模块: {offenders}"


# ── 2. 消全局守卫(ast): _CURRENT_MARKET_REGIME 不作为活代码标识符出现 ──
#    (docstring 里提到该名是说明"已消除", 属文档不算活代码; 故走 ast Name/Global, 非裸字符串)
def test_api_no_current_market_regime_global():
    tree = ast.parse(_API_PY.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Global) and "_CURRENT_MARKET_REGIME" in node.names:
            offenders.append("global")
        if isinstance(node, ast.Name) and node.id == "_CURRENT_MARKET_REGIME":
            offenders.append("Name")
    assert offenders == [], f"api.py 不应有 _CURRENT_MARKET_REGIME 活代码: {offenders}"


def _client_and_api():
    if not _HAS_FASTAPI:
        raise _SkipTest("无 fastapi/httpx, 跳过 TestClient 测(VPS venv 实跑)")
    import vaxstock.services.api as api
    from fastapi.testclient import TestClient
    return api, TestClient(api.app)


# ── 3. lite 前置: lite=1 必须在 refresh_regime 之前 return(冷缓存防卡) ──
def test_lite_returns_before_refresh_regime():
    api, client = _client_and_api()
    saved_refresh = api.refresh_regime
    saved_lite = api.build_lite_item
    called = {"refresh": False}
    try:
        def _spy_refresh(force=False):
            called["refresh"] = True
            return {"ts": 0.0, "regime": "momentum", "overview": {}}

        api.refresh_regime = _spy_refresh
        api.build_lite_item = lambda code: {"code": code, "lite": True}

        r = client.get("/analyze/600000?lite=1")
        assert r.status_code == 200, r.text
        assert r.json()["lite"] is True
        assert called["refresh"] is False, "lite 分支不应触发 refresh_regime(应前置 return)"
    finally:
        api.refresh_regime = saved_refresh
        api.build_lite_item = saved_lite


# ── 4. analyze 非 lite: regime 显式传 build_stock_item(非全局) ──
def test_analyze_passes_regime_explicitly():
    api, client = _client_and_api()
    saved = (api.refresh_regime, api.build_stock_item, api._bump_cap, api._get_source)
    cap = {}
    try:
        api.refresh_regime = lambda force=False: {"ts": 1e18, "regime": "value", "overview": {}}
        api._bump_cap = lambda: None
        api._get_source = lambda: "STUB_SRC"

        def _spy_build(group, code, name, cost, shares, source=None,
                       market_regime="momentum", manual_concepts=None):
            cap["market_regime"] = market_regime
            cap["source"] = source
            return {"code": code, "regime": market_regime}

        api.build_stock_item = _spy_build

        r = client.get("/analyze/600000")
        assert r.status_code == 200, r.text
        assert cap["market_regime"] == "value", "regime 应显式传入 build_stock_item"
        assert cap["source"] == "STUB_SRC", "source 应来自 _get_source()"
        assert r.json()["regime"] == "value"
    finally:
        api.refresh_regime, api.build_stock_item, api._bump_cap, api._get_source = saved


# ── 5. watch 原子写: replace 写 tmp 文件, list 读回一致 ──
def test_watch_replace_and_list_roundtrip():
    api, client = _client_and_api()
    d = tempfile.mkdtemp(prefix="vaxapi_")
    saved_path = api.WATCH_RULES_FILE
    try:
        api.WATCH_RULES_FILE = os.path.join(d, "watch_rules.json")
        rules = [{"code": "600000", "name": "浦发银行", "type": "price_below",
                  "level": 10.0, "note": "测试"}]
        r = client.post("/watch/replace", json=rules)
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 1
        # 落盘文件确实写了
        assert os.path.isfile(api.WATCH_RULES_FILE)
        # list 读回一致
        r2 = client.get("/watch/list")
        assert r2.status_code == 200
        got = r2.json()
        assert len(got) == 1 and got[0]["code"] == "600000" and got[0]["level"] == 10.0
    finally:
        api.WATCH_RULES_FILE = saved_path
        shutil.rmtree(d, ignore_errors=True)


def test_health_no_source_construction():
    """/health 只 peek 单例, 不强制构造 TushareSource(不连网)。"""
    api, client = _client_and_api()
    saved = api._src
    try:
        api._src = None  # 未构造
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["tushare_points"] == 0  # 未构造 -> 0, 未触发构造
        assert api._src is None, "/health 不应构造 source"
    finally:
        api._src = saved


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
