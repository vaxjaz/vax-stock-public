# -*- coding: utf-8 -*-
"""OpenAI-compatible Codex HTTP client.

Wall-clock timeout. By default any error returns None. This module does not read
runtime configuration or make network calls at import time; callers pass
url/model/token from config.SECRETS.
"""

import logging
import re
from typing import Any, Iterable, List, Optional

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


def _model_unavailable(message: str, code) -> bool:
    msg = str(message or "").lower()
    err_code = str(code or "").lower()
    markers = (
        "unknown provider for model",
        "model not found",
        "model_not_found",
        "unknown model",
        "unsupported model",
        "does not exist",
    )
    return any(m in msg or m in err_code for m in markers)


def _response_message(payload: Any) -> tuple[str, Any]:
    """Extract a provider error without assuming the OpenAI error envelope."""
    if not isinstance(payload, dict):
        return "", None
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or ""), error.get("code")
    if isinstance(error, str):
        return error, payload.get("code")
    return str(payload.get("message") or payload.get("detail") or ""), payload.get("code")


def _http_error_type(status_code, message: str, code) -> tuple[str, bool]:
    if _model_unavailable(message, code):
        return "model_unavailable", True
    if _provider_unavailable(status_code, message, code):
        return "provider_unavailable", True
    if status_code in {400, 404, 413, 422}:
        # Some OpenAI-compatible gateways return an empty/non-standard 4xx
        # body for a model-specific rejection. The caller may safely try the
        # next finite catalog candidate, but must still preserve the failure.
        return "request_rejected", True
    if status_code in {401, 403}:
        return "auth_failed", False
    return "http_error", False


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


def extract_model_ids(payload: Any) -> List[str]:
    """Extract model ids from common OpenAI-compatible catalog shapes."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and item.get("id")
        ]
    models = payload.get("models")
    if isinstance(models, list):
        return [
            str(item.get("id") if isinstance(item, dict) else item)
            for item in models
            if (isinstance(item, str) and item) or (
                isinstance(item, dict) and item.get("id")
            )
        ]
    return []


def _eligible_chat_model(model_id: str) -> bool:
    value = str(model_id or "").strip().lower()
    if not value or not ("gpt" in value or "codex" in value):
        return False
    excluded = (
        "embedding",
        "moderation",
        "audio",
        "realtime",
        "transcribe",
        "tts",
        "image",
    )
    return not any(marker in value for marker in excluded)


def _model_sort_key(model_id: str):
    """Deterministic name-based lightweight preference, not a pricing claim."""
    value = str(model_id).lower()
    if "nano" in value:
        size_rank = 0
    elif "mini" in value:
        size_rank = 1
    elif "spark" in value:
        size_rank = 2
    else:
        size_rank = 3
    version = tuple(int(part) for part in re.findall(r"\d+", value)[:3])
    padded = version + (0,) * (3 - len(version))
    return (size_rank, tuple(-part for part in padded), value)


def select_chat_model_candidates(
    available_models: Iterable[str], *, preferred: Optional[str] = None,
    fallback: Optional[str] = None,
) -> List[str]:
    """Return unique chat-model candidates with lightweight ids first.

    When discovery yields no eligible ids, the explicit configured models are
    retained so a temporary /models failure does not disable the worker.
    """
    available = {
        str(model).strip()
        for model in available_models or []
        if _eligible_chat_model(str(model))
    }
    if available:
        return sorted(available, key=_model_sort_key)

    configured: List[str] = []
    for model in (preferred, fallback):
        value = str(model or "").strip()
        if not value or value.lower() == "auto" or value in configured:
            continue
        configured.append(value)
    return configured


def list_codex_models(url: str, token: str, timeout: int = 10) -> List[str]:
    """Read the live OpenAI-compatible model catalog without caching."""
    models_url = models_url_from_chat_url(url)
    if not (models_url and token):
        raise CodexCallError(
            "codex model discovery config missing",
            error_type="config_missing",
            retryable=False,
        )
    try:
        resp = _requests_module().get(
            models_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        status_code = getattr(resp, "status_code", 200)
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            err = data.get("error") or {}
            msg = str(err.get("message") or "")
            code = err.get("code")
            raise CodexCallError(
                msg or "codex model discovery returned error",
                status_code=status_code,
                code=code,
                error_type="provider_unavailable" if _provider_unavailable(
                    status_code, msg, code
                ) else "server_error",
                retryable=_provider_unavailable(status_code, msg, code),
            )
        if isinstance(status_code, int) and status_code >= 400:
            raise CodexCallError(
                f"codex model discovery HTTP error: status={status_code}",
                status_code=status_code,
                error_type="provider_unavailable" if _provider_unavailable(
                    status_code, "", None
                ) else "http_error",
                retryable=_provider_unavailable(status_code, "", None),
            )
        model_ids = extract_model_ids(data)
        if not model_ids:
            raise CodexCallError(
                "codex model discovery returned no model ids",
                status_code=status_code,
                error_type="bad_response",
                retryable=True,
            )
        return model_ids
    except CodexCallError:
        raise
    except Exception as exc:
        raise CodexCallError(
            str(exc), error_type="request_exception", retryable=True
        ) from exc


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
            response_text = str(getattr(resp, "text", "") or "").strip()
            logger.warning(
                "codex non-json response: status=%s model=%s body=%s err=%s",
                status_code,
                model,
                response_text[:160],
                str(e)[:120],
            )
            if raise_on_error:
                message = response_text or str(e)
                error_type, retryable = _http_error_type(
                    status_code, message, None
                )
                raise CodexCallError(
                    message,
                    status_code=status_code,
                    error_type=error_type if status_code >= 400 else "bad_response",
                    retryable=retryable if status_code >= 400 else False,
                )
            return None
        msg, code = _response_message(data)
        has_error_envelope = isinstance(data, dict) and bool(data.get("error"))
        if has_error_envelope or (
            isinstance(status_code, int) and status_code >= 400
        ):
            error_type, retryable = _http_error_type(status_code, msg, code)
            if has_error_envelope and error_type == "http_error":
                error_type = "server_error"
            logger.warning(
                "codex returned error: status=%s model=%s message=%s code=%s",
                status_code,
                model,
                (msg or str(data))[:160],
                code,
            )
            if raise_on_error:
                raise CodexCallError(
                    msg or f"codex HTTP error: status={status_code}",
                    status_code=status_code,
                    code=code,
                    error_type=error_type,
                    retryable=retryable,
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
