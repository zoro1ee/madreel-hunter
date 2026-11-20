"""Generic webhook target.

MoviePilot, n8n, Home Assistant automations and self-hosted notifiers all accept
a JSON POST, so one small helper covers them. The payload is intentionally flat
and stable; map it on the receiving side.
"""

from __future__ import annotations

from typing import Any

from ..http import request


class WebhookError(RuntimeError):
    pass


def post_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    token: str = "",
    timeout: float = 15.0,
    proxy: str = "",
    header_name: str = "Authorization",
) -> int:
    """POST ``payload`` to ``url`` and return the HTTP status code."""
    headers: dict[str, str] = {}
    if token:
        headers[header_name] = f"Bearer {token}" if header_name == "Authorization" else token
    resp = request("POST", url, json_body=payload, headers=headers or None, timeout=timeout, proxy=proxy)
    if resp.status >= 400:
        raise WebhookError(f"webhook returned HTTP {resp.status}: {resp.text[:200]}")
    return resp.status
