# -*- coding: utf-8 -*-
"""services.pool_admin 测试(观察池写模块, 零网络, tmp 文件 monkeypatch)+ 结构隔离守卫(ast)。"""

import ast
import json
import pathlib
import shutil
import tempfile

import vaxstock.services.pool_admin as pa

_REPO = pathlib.Path(__file__).resolve().parents[2]

_SEED = {
    "_说明": "保留我", "data_sources": {"tushare_enabled": True},
    "holdings": {}, "watchlist": {"688256": {"name": "寒武纪", "concepts": ["AI算力"]}},
    "hot_sectors": ["AI算力"],
}


class _Src:
    def get_stock_concepts(self, code):
        return ["白酒", "消费"]


def _setup(d, seed=True):
    saved = (pa.WATCHLIST_FILE, pa.AUDIT_FILE, pa.get_sina_realtime)
    pa.WATCHLIST_FILE = pathlib.Path(d) / "watchlist.json"
    pa.AUDIT_FILE = pathlib.Path(d) / "pool_audit.jsonl"
    pa.get_sina_realtime = lambda code, exp="": {"name": "贵州茅台"}
    if seed:
        pa.WATCHLIST_FILE.write_text(json.dumps(_SEED, ensure_ascii=False), encoding="utf-8")
    return saved


def _teardown(saved):
    pa.WATCHLIST_FILE, pa.AUDIT_FILE, pa.get_sina_realtime = saved


def _data():
    return json.loads(pa.WATCHLIST_FILE.read_text(encoding="utf-8"))


def _audit_actions():
    if not pa.AUDIT_FILE.exists():
        return []
    return [json.loads(l)["action"] for l in pa.AUDIT_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── list ──
def test_list_pool():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        pool = pa.list_pool()
        assert pool["count"] == 1
        assert pool["watchlist"]["688256"]["concepts"] == ["AI算力"]
        assert pool["focus"] == ["AI算力"]
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── propose 不写 ──
def test_propose_add_preview_no_write():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        pv = pa.propose_add("600519", ["白酒"], source=_Src())
        assert pv["name"] == "贵州茅台" and pv["concepts"] == ["白酒"]
        assert pv["concepts_status"] == "用户提供"
        assert _data()["watchlist"].get("600519") is None        # preview 不落盘
        # 不给概念 -> Tushare 兜底标待确认
        pv2 = pa.propose_add("000001", None, source=_Src())
        assert pv2["concepts"] == ["白酒", "消费"] and "待确认" in pv2["concepts_status"]
        assert _audit_actions() == []                             # propose 不写审计
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── commit 写 + 保留既有键 + 审计 ──
def test_commit_add_writes_preserves_audits():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        assert pa.commit_add("600519", ["白酒", "消费"], source=_Src()) is True
        data = _data()
        assert data["watchlist"]["600519"]["concepts"] == ["白酒", "消费"]
        assert data["watchlist"]["600519"]["name"] == "贵州茅台"
        # 既有键全部保留(不覆盖损坏)
        assert data["_说明"] == "保留我" and "data_sources" in data
        assert "688256" in data["watchlist"]                      # 原票还在
        assert _audit_actions() == ["add"]
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


def test_commit_add_tushare_fallback_when_no_concepts():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        pa.commit_add("000001", None, source=_Src())              # 不给概念 -> Tushare 兜底
        assert _data()["watchlist"]["000001"]["concepts"] == ["白酒", "消费"]
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


def test_commit_add_rejects_empty_concepts():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        try:
            pa.commit_add("000002", None, source=None)            # 无概念且无兜底
            assert False, "应抛 PoolError"
        except pa.PoolError:
            pass
        assert _data()["watchlist"].get("000002") is None         # 拒绝后未写
        assert _audit_actions() == []
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── remove ──
def test_remove():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        assert pa.remove("688256") is True
        assert "688256" not in _data()["watchlist"]
        assert _audit_actions() == ["remove"]
        try:
            pa.remove("999999"); assert False, "删不存在应抛"
        except pa.PoolError:
            pass
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── update_concepts ──
def test_update_concepts():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        pa.update_concepts("688256", ["AI算力", "AI芯片", "国产替代"])
        assert _data()["watchlist"]["688256"]["concepts"] == ["AI算力", "AI芯片", "国产替代"]
        for bad in (lambda: pa.update_concepts("688256", []),       # 空概念
                    lambda: pa.update_concepts("000003", ["x"])):    # 不在池
            try:
                bad(); assert False, "应抛 PoolError"
            except pa.PoolError:
                pass
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── set_focus ──
def test_set_focus():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d)
    try:
        pa.set_focus(["AI算力", "光模块"])
        assert _data()["hot_sectors"] == ["AI算力", "光模块"]
        pa.set_focus([])                                          # 空=清空, 合法
        assert _data()["hot_sectors"] == []
        assert _audit_actions() == ["set_focus", "set_focus"]
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── 读损坏文件拒绝写(防覆盖) ──
def test_corrupt_watchlist_refuses_write():
    d = tempfile.mkdtemp(prefix="vaxpool_")
    saved = _setup(d, seed=False)
    try:
        pa.WATCHLIST_FILE.write_text("{坏的 json", encoding="utf-8")
        try:
            pa.commit_add("600519", ["白酒"], source=_Src()); assert False, "损坏应拒绝"
        except pa.PoolError:
            pass
    finally:
        _teardown(saved); shutil.rmtree(d, ignore_errors=True)


# ── 结构隔离守卫(ast): 盘中链路不 import pool_admin ──
def test_structure_isolation_no_pool_admin_in_intraday_chain():
    targets = [
        _REPO / "src" / "vaxstock" / "services" / "intraday.py",
        _REPO / "src" / "vaxstock" / "sources" / "codex.py",
        _REPO / "src" / "vaxstock" / "services" / "forecast_recorder.py",
    ]
    offenders = []
    for py in targets:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            toks = []
            if isinstance(node, ast.ImportFrom):
                toks.append(node.module or "")
                toks.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                toks.extend(a.name for a in node.names)
            if any("pool_admin" in t for t in toks):
                offenders.append(py.name)
    assert offenders == [], f"盘中链路不应 import pool_admin: {offenders}"


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn(); print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1; print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1; print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
