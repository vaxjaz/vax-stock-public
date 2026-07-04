# -*- coding: utf-8 -*-
"""OpenAI-compatible Codex HTTP client.

Wall-clock timeout. Any error returns None. This module does not read runtime
configuration or make network calls at import time; callers pass url/model/token
from config.SECRETS.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _requests_module():
    import requests
    return requests


def normalize_chat_completions_url(url: str) -> str:
    """Normalize OpenAI-compatible URL to /v1/chat/completions."""
    u = str(url or "").strip()
    if not u:
        return ""
    u = u.rstrip("/")
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    return u


def models_url_from_chat_url(url: str) -> str:
    """Return the sibling /v1/models URL for diagnostics."""
    u = normalize_chat_completions_url(url)
    if u.endswith("/chat/completions"):
        return u[: -len("/chat/completions")] + "/models"
    if u.endswith("/v1"):
        return f"{u}/models"
    return u.rstrip("/") + "/models" if u else ""


def _token_len(token: str) -> int:
    return len(str(token or ""))


def call_codex(system_prompt: str, user_msg: str, *,
               url: str, model: str, token: str, timeout: int = 30) -> Optional[str]:
    """Call Codex and return stripped message content. Failure/timeout -> None."""
    normalized_url = normalize_chat_completions_url(url)
    if not (normalized_url and model and token):
        logger.warning(
            "codex config missing: url_present=%s model_present=%s token_present=%s token_len=%s",
            bool(normalized_url),
            bool(model),
            bool(token),
            _token_len(token),
        )
        return None
    try:
        resp = _requests_module().post(
            normalized_url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "stream": False,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=timeout,
        )
        status_code = getattr(resp, "status_code", 200)
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            err = data.get("error") or {}
            logger.warning(
                "codex returned error: status=%s model=%s message=%s code=%s",
                status_code,
                model,
                str(err.get("message") or "")[:160],
                err.get("code"),
            )
            return None
        if isinstance(status_code, int) and status_code >= 400:
            logger.warning("codex HTTP error: status=%s model=%s url=%s", status_code, model, normalized_url)
            return None
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"codex call failed: model={model} url={normalized_url} err={str(e)[:160]}")
        return None
