# -*- coding: utf-8 -*-
"""Codex local endpoint diagnostics.

Usage on VPS:
    PYTHONPATH=src python -m vaxstock.services.codex_probe

The probe prints whether CODEX_* environment variables are present, what
config.SECRETS finally resolved, whether the configured model appears in
/v1/models, and whether a tiny chat completion returns choices.  It never
prints the token value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from vaxstock import config
from vaxstock.sources.codex import models_url_from_chat_url, normalize_chat_completions_url


_ENV_NAMES = {
    "codex_url": "CODEX_URL",
    "codex_model": "CODEX_MODEL",
    "codex_token": "CODEX_TOKEN",
    "codex_timeout": "CODEX_TIMEOUT",
}


def _env_state(name: str) -> str:
    val = os.getenv(name)
    if val is None:
        return "missing"
    if val == "":
        return "empty"
    return "set"


def _token_desc(token: Any) -> str:
    token_s = str(token or "")
    return f"present={bool(token_s)} len={len(token_s)}"


def _json_or_text(resp) -> Any:
    try:
        return resp.json()
    except Exception:
        return getattr(resp, "text", "")


def _extract_model_ids(payload: Any) -> List[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [str(x.get("id")) for x in data if isinstance(x, dict) and x.get("id")]
    models = payload.get("models")
    if isinstance(models, list):
        return [str(x.get("id") if isinstance(x, dict) else x) for x in models]
    return []


def _error_summary(payload: Any) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        err = payload["error"]
        return f"message={err.get('message')} code={err.get('code')} type={err.get('type')}"
    if isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)[:500]
    return str(payload)[:500]


def _print_config(timeout_override: Optional[int]) -> Dict[str, Any]:
    s = config.SECRETS
    timeout = int(timeout_override if timeout_override is not None else s.get("codex_timeout", 30))
    raw_url = s.get("codex_url") or ""
    model = s.get("codex_model") or ""
    token = s.get("codex_token") or ""
    chat_url = normalize_chat_completions_url(raw_url)
    models_url = models_url_from_chat_url(raw_url)

    print("Codex config probe")
    print(f"- secrets_file: {config.SECRETS_FILE}")
    for field, env_name in _ENV_NAMES.items():
        print(f"- env {env_name}: {_env_state(env_name)}")
    print(f"- config.codex_url: {raw_url or 'MISSING'}")
    print(f"- normalized_chat_url: {chat_url or 'MISSING'}")
    print(f"- models_url: {models_url or 'MISSING'}")
    print(f"- config.codex_model: {model or 'MISSING'}")
    print(f"- config.codex_token: {_token_desc(token)}")
    print(f"- config.codex_timeout: {timeout}")
    return {
        "chat_url": chat_url,
        "models_url": models_url,
        "model": model,
        "token": token,
        "timeout": timeout,
    }


def _requests_module():
    import requests
    return requests


def _headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def probe_models(models_url: str, model: str, token: str, timeout: int, *, limit: int = 30) -> int:
    print("\n[models] GET /v1/models")
    if not (models_url and token):
        print("- skipped: models_url/token missing")
        return 2
    try:
        resp = _requests_module().get(models_url, headers=_headers(token), timeout=timeout)
        payload = _json_or_text(resp)
        print(f"- status: {getattr(resp, 'status_code', 'unknown')}")
        if isinstance(payload, dict) and payload.get("error"):
            print(f"- error: {_error_summary(payload)}")
            return 4
        ids = _extract_model_ids(payload)
        if ids:
            shown = ids[:limit]
            suffix = "" if len(ids) <= limit else f" ... (+{len(ids) - limit} more)"
            print(f"- model_ids: {', '.join(shown)}{suffix}")
            if model:
                print(f"- configured_model_in_list: {model in ids}")
                return 0 if model in ids else 3
            return 2
        print(f"- response: {_error_summary(payload)}")
        return 1
    except Exception as e:
        print(f"- request_error: {type(e).__name__}: {str(e)[:300]}")
        return 4


def probe_chat(chat_url: str, model: str, token: str, timeout: int) -> int:
    print("\n[chat] POST /v1/chat/completions")
    if not (chat_url and model and token):
        print("- skipped: chat_url/model/token missing")
        return 2
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Return only {\"ok\":true}"}],
        "temperature": 0.2,
        "stream": False,
    }
    try:
        resp = _requests_module().post(chat_url, json=payload, headers=_headers(token), timeout=timeout)
        data = _json_or_text(resp)
        print(f"- status: {getattr(resp, 'status_code', 'unknown')}")
        if isinstance(data, dict) and data.get("error"):
            print(f"- error: {_error_summary(data)}")
            return 4
        if isinstance(data, dict) and data.get("choices"):
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            print("- choices: present")
            print(f"- content: {content[:300]}")
            return 0
        print(f"- response_without_choices: {_error_summary(data)}")
        return 5
    except Exception as e:
        print(f"- request_error: {type(e).__name__}: {str(e)[:300]}")
        return 4


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe local Codex OpenAI-compatible endpoint config.")
    parser.add_argument("--timeout", type=int, default=None, help="Override request timeout seconds.")
    parser.add_argument("--no-chat", action="store_true", help="Only check config and /v1/models.")
    parser.add_argument("--models-limit", type=int, default=30, help="Max model ids to print.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = _print_config(args.timeout)
    missing = [k for k in ("chat_url", "model", "token") if not cfg.get(k)]
    if missing:
        print(f"\n[config] missing required: {', '.join(missing)}")
        return 2

    model_rc = probe_models(
        cfg["models_url"],
        cfg["model"],
        cfg["token"],
        cfg["timeout"],
        limit=max(1, args.models_limit),
    )
    if args.no_chat:
        return model_rc

    chat_rc = probe_chat(cfg["chat_url"], cfg["model"], cfg["token"], cfg["timeout"])
    return chat_rc if chat_rc != 0 else model_rc


if __name__ == "__main__":
    sys.exit(main())
