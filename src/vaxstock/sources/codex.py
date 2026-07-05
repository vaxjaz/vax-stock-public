# -*- coding: utf-8 -*-
"""OpenAI-compatible Codex HTTP client.

Wall-clock timeout. By default any error returns None. This module does not read
runtime configuration or make network calls at import time; callers pass
url/model/token from config.SECRETS.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CodexCallError(RuntimeError):
    """Structured Codex transport/provider failure."""

    def __init__(self, message: str, *, status_code=None, code=None,
                 error_type: str = "request_failed", retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.error_type = error_type
        self.retryable = retryable


def _provider_unavailable(status_code, message: str, code) -> bool:
    msg = str(message or "").lower()
    err_code = str(code or "").lower()
    if status_code in {502, 503, 504}:
        return True
    markers = (
        "auth_unavailable",
        "no auth available",
        "upstream connect error",
        "disconnect/reset",
        "transport failure",
        "connection failure",
    )
    return any(m in msg or m in err_code for m in markers)


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
               url: str, model: str, token: str, timeout: int = 30,
               raise_on_error: bool = False) -> Optional[str]:
    """Call Codex and return stripped message content.

    Historical behavior is preserved: failure/timeout returns None. Callers that
    must distinguish provider/auth outages can set ``raise_on_error=True`` and
    catch ``CodexCallError``.
    """
    normalized_url = normalize_chat_completions_url(url)
    if not (normalized_url and model and token):
        logger.warning(
            "codex config missing: url_present=%s model_present=%s token_present=%s token_len=%s",
            bool(normalized_url),
            bool(model),
            bool(token),
            _token_len(token),
        )
        if raise_on_error:
            raise CodexCallError("codex config missing", error_type="config_missing", retryable=False)
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
        try:
            data = resp.json()
        except Exception as e:
            logger.warning("codex non-json response: status=%s model=%s err=%s", status_code, model, str(e)[:120])
            if raise_on_error:
                unavailable = _provider_unavailable(status_code, str(e), None)
                raise CodexCallError(
                    str(e),
                    status_code=status_code,
                    error_type="provider_unavailable" if unavailable else "bad_response",
                    retryable=unavailable,
                )
            return None
        if isinstance(data, dict) and data.get("error"):
            err = data.get("error") or {}
            msg = str(err.get("message") or "")
            code = err.get("code")
            unavailable = _provider_unavailable(status_code, msg, code)
            logger.warning(
                "codex returned error: status=%s model=%s message=%s code=%s",
                status_code,
                model,
                msg[:160],
                code,
            )
            if raise_on_error:
                raise CodexCallError(
                    msg or "codex returned error",
                    status_code=status_code,
                    code=code,
                    error_type="provider_unavailable" if unavailable else "server_error",
                    retryable=unavailable,
                )
            return None
        if isinstance(status_code, int) and status_code >= 400:
            logger.warning("codex HTTP error: status=%s model=%s url=%s", status_code, model, normalized_url)
            if raise_on_error:
                unavailable = _provider_unavailable(status_code, "", None)
                raise CodexCallError(
                    f"codex HTTP error: status={status_code}",
                    status_code=status_code,
                    error_type="provider_unavailable" if unavailable else "http_error",
                    retryable=unavailable,
                )
            return None
        return data["choices"][0]["message"]["content"].strip()
    except CodexCallError:
        raise
    except Exception as e:
        logger.warning(f"codex call failed: model={model} url={normalized_url} err={str(e)[:160]}")
        if raise_on_error:
            raise CodexCallError(str(e), error_type="request_exception", retryable=True)
        return None
