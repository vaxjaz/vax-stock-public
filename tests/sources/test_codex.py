# -*- coding: utf-8 -*-
"""sources.codex tests. No network; requests.post is monkeypatched."""

import vaxstock.sources.codex as codex


class _Resp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code

    def json(self):
        return self._p


class _Requests:
    def __init__(self, post):
        self.post = post


def _patch_post(fn):
    saved = codex._requests_module
    codex._requests_module = lambda: _Requests(fn)
    return saved


def test_normalize_chat_completions_url_accepts_v1_base():
    assert codex.normalize_chat_completions_url("http://x/v1") == "http://x/v1/chat/completions"
    assert codex.normalize_chat_completions_url("http://x/v1/") == "http://x/v1/chat/completions"
    assert codex.normalize_chat_completions_url("http://x/v1/chat/completions") == "http://x/v1/chat/completions"


def test_models_url_from_chat_url():
    assert codex.models_url_from_chat_url("http://x/v1") == "http://x/v1/models"
    assert codex.models_url_from_chat_url("http://x/v1/chat/completions") == "http://x/v1/models"


def test_call_codex_parses_content_and_normalizes_url():
    seen = {}
    def _post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        return _Resp({"choices": [{"message": {"content": "  intraday: watch  "}}]})
    saved = _patch_post(_post)
    try:
        out = codex.call_codex("sys", "user", url="http://x/v1", model="codex", token="t")
        assert out == "intraday: watch"
        assert seen["url"] == "http://x/v1/chat/completions"
        assert seen["headers"]["Authorization"] == "Bearer t"
    finally:
        codex._requests_module = saved


def test_call_codex_returns_none_on_missing_config():
    assert codex.call_codex("s", "u", url="http://x/v1", model="", token="t") is None
    assert codex.call_codex("s", "u", url="http://x/v1", model="m", token="") is None
    assert codex.call_codex("s", "u", url="", model="m", token="t") is None


def test_call_codex_returns_none_on_server_error_payload():
    saved = _patch_post(lambda *a, **k: _Resp(
        {"error": {"message": "unknown provider for model", "code": "internal_server_error"}},
        status_code=500,
    ))
    try:
        assert codex.call_codex("s", "u", url="http://x/v1", model="bad", token="t") is None
    finally:
        codex._requests_module = saved


def test_call_codex_returns_none_on_exception():
    def _boom(*a, **k):
        raise TimeoutError("timeout")
    saved = _patch_post(_boom)
    try:
        assert codex.call_codex("s", "u", url="http://x", model="m", token="t") is None
    finally:
        codex._requests_module = saved


def test_call_codex_returns_none_on_bad_shape():
    saved = _patch_post(lambda *a, **k: _Resp({"unexpected": True}))
    try:
        assert codex.call_codex("s", "u", url="http://x", model="m", token="t") is None
    finally:
        codex._requests_module = saved


def test_import_codex_no_connect():
    """Importing codex.py should not open sockets or import requests."""
    import importlib
    import socket
    import sys
    orig_connect = socket.socket.connect
    orig_requests = sys.modules.pop("requests", None)

    def _no_net(*a, **k):
        raise AssertionError("network during import")

    socket.socket.connect = _no_net
    try:
        importlib.reload(codex)
    finally:
        socket.socket.connect = orig_connect
        if orig_requests is not None:
            sys.modules["requests"] = orig_requests
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
