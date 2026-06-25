# -*- coding: utf-8 -*-
"""codex HTTP 客户端(OpenAI 兼容 /v1/chat/completions)。

墙钟超时, 任何异常/超时返回 None(不抛, 不 fallback)。
不在模块顶层读配置、不连网; url/model/token 由调用方从 config.SECRETS 传入。
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def call_codex(system_prompt: str, user_msg: str, *,
               url: str, model: str, token: str, timeout: int = 30) -> Optional[str]:
    """调 codex(OpenAI 兼容), 返回 message content(strip 后); 失败/超时 -> None。"""
    try:
        resp = requests.post(
            url,
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
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"codex 调用失败: {str(e)[:120]}")
        return None
