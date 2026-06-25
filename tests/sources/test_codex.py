# -*- coding: utf-8 -*-
"""sources.codex 测试(零网络, monkeypatch requests.post)。"""

import vaxstock.sources.codex as codex


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_call_codex_parses_content():
    saved = codex.requests.post
    try:
        codex.requests.post = lambda url, json=None, headers=None, timeout=None: _Resp(
            {"choices": [{"message": {"content": "  盘中倾向: 观察  "}}]})
        out = codex.call_codex("sys", "user", url="http://x/v1", model="codex", token="t")
        assert out == "盘中倾向: 观察"  # strip 后
    finally:
        codex.requests.post = saved


def test_call_codex_returns_none_on_exception():
    saved = codex.requests.post

    def _boom(*a, **k):
        raise TimeoutError("连接超时")

    try:
        codex.requests.post = _boom
        assert codex.call_codex("s", "u", url="http://x", model="m", token="t") is None
    finally:
        codex.requests.post = saved


def test_call_codex_returns_none_on_bad_shape():
    saved = codex.requests.post
    try:
        codex.requests.post = lambda *a, **k: _Resp({"unexpected": True})
        assert codex.call_codex("s", "u", url="http://x", model="m", token="t") is None
    finally:
        codex.requests.post = saved


def test_import_codex_no_connect():
    """codex.py 顶层不连网: socket guard 下 reload 模块仍成功。"""
    import importlib
    import socket
    orig = socket.socket.connect

    def _no_net(*a, **k):
        raise AssertionError("import 期间连网")

    socket.socket.connect = _no_net
    try:
        importlib.reload(codex)
    finally:
        socket.socket.connect = orig
    assert callable(codex.call_codex)


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
