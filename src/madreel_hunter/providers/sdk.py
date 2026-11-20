"""Adapter around the official ``dian115_openapi`` SDK.

The SDK performs envelope encryption, HMAC proof generation, anti-replay fields
and response decryption. We never re-implement those: this module only maps our
own models onto whatever call shape the installed SDK exposes.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from ..config import Config
from ..models import Share, UnlockResult
from .base import OpenApiError, SdkNotInstalled

SDK_MODULE_CANDIDATES = ("dian115_openapi", "dian115openapi")
SDK_CLIENT_CANDIDATES = ("Dian115OpenAPI", "Client", "Dian115Client")


def sdk_available() -> bool:
    return _import_sdk() is not None


def _import_sdk() -> Any | None:
    for name in SDK_MODULE_CANDIDATES:
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    return None


def _unwrap(value: Any) -> Any:
    """SDKs in the wild return either the payload or a wrapper with ``data``."""
    if isinstance(value, dict) and "data" in value and len(value) <= 3:
        data = value.get("data")
        if isinstance(data, dict):
            return data
    return value


class SdkProvider:
    """Business calls through the official SDK."""

    def __init__(self, config: Config) -> None:
        module = _import_sdk()
        if module is None:
            raise SdkNotInstalled()
        client_cls = None
        for attr in SDK_CLIENT_CANDIDATES:
            client_cls = getattr(module, attr, None)
            if client_cls is not None:
                break
        if client_cls is None:
            raise SdkNotInstalled()
        self._client = client_cls(base_url=config.base_url, api_key=config.require_api_key())
        self._config = config

    def _call(self, *names: str, **kwargs: Any) -> Any:
        for name in names:
            method: Callable[..., Any] | None = getattr(self._client, name, None)
            if callable(method):
                try:
                    return _unwrap(method(**kwargs))
                except TypeError:
                    continue
                except Exception as exc:  # SDK specific error types
                    raise self._translate(exc) from exc
        raise OpenApiError("sdk_method_missing", f"installed SDK has none of: {', '.join(names)}")

    @staticmethod
    def _translate(exc: Exception) -> OpenApiError:
        code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        message = getattr(exc, "msg", None) or str(exc)
        return OpenApiError(str(code or "sdk_error"), str(message), getattr(exc, "status", None))

    def me(self) -> dict[str, Any]:
        return self._call("me")

    def signin(self, mode: str = "normal") -> dict[str, Any]:
        return self._call("signin", mode=mode)

    def list_shares(self, payload: dict[str, Any]) -> list[Share]:
        data = self._call("list_shares", **payload)
        items = data.get("items", []) if isinstance(data, dict) else []
        return [Share.from_api(item) for item in items]

    def unlock(self, share_id: int, resource_id: int | None = None) -> UnlockResult:
        payload: dict[str, Any] = {"share_id": share_id}
        if resource_id is not None:
            payload["resource_id"] = resource_id
        data = self._call("unlock", **payload) or {}
        return UnlockResult(
            share_id=share_id,
            resource_id=resource_id,
            share_url=data.get("share_url") or data.get("url"),
            password=data.get("password") or data.get("share_password"),
            kind=data.get("share_kind") or data.get("kind"),
            created_at=data.get("created_at"),
            raw=data if isinstance(data, dict) else {},
        )

    def rss(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("rss", **payload) or {}

    def share(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("share", **payload) or {}

    def check_sharecode(self, share_code: str) -> dict[str, Any]:
        return self._call("check_sharecode", share_code=share_code) or {}
