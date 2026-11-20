"""Minimal stdlib HTTP helper (no third-party dependencies)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None


def request(
    method: str,
    url: str,
    *,
    json_body: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    proxy: str = "",
    ua: str = DEFAULT_UA,
) -> Response:
    """Perform an HTTP request and always return a Response (never raise on 4xx/5xx)."""
    data: bytes | None = None
    final_headers = {"User-Agent": ua, "Accept": "application/json, text/plain, */*"}
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        final_headers["Content-Type"] = "application/json"
    if headers:
        final_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=final_headers, method=method)
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    ctx = ssl.create_default_context()
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)

    try:
        with opener.open(req, timeout=timeout) as resp:
            return Response(resp.status, dict(resp.headers), resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a body worth reading
        return Response(exc.code, dict(exc.headers or {}), exc.read())
    except urllib.error.URLError as exc:
        raise ConnectionError(f"request to {url} failed: {exc.reason}") from exc
