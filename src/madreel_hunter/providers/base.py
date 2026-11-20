"""Provider abstraction.

The MADREEL OpenAPI v2 only accepts requests wrapped in an encrypted envelope
whose keys are derived from *both* the user's OpenAPI key and a sealed SDK
token. That sealed identity ships only inside the official SDK handed to
approved developer applications, so every business call must go through it.

``SdkProvider`` therefore delegates to the official SDK when it is installed and
raises an actionable error when it is not. Everything that does *not* need the
SDK (TMDB search, tag parsing, scoring, probing, export) lives outside this
package so the tool stays useful before approval.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..models import Share, UnlockResult


class OpenApiError(RuntimeError):
    """A structured error returned by the portal."""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{code}: {message}" if code else message)


class SdkNotInstalled(OpenApiError):
    def __init__(self) -> None:
        super().__init__(
            "sdk_not_installed",
            "The official MADREEL SDK is not installed. OpenAPI v2 requires the "
            "sealed SDK identity (developer_application_id / sdk_identity / "
            "package_id / package_fingerprint) plus SDK-derived keys, which "
            "cannot be re-implemented client side. Apply for a developer "
            "application at https://madow.tv/openapiv2 and drop the resulting "
            "dian115_openapi package into your environment.",
        )


class Provider(Protocol):
    """Minimal business surface used by the CLI."""

    def me(self) -> dict[str, Any]: ...

    def signin(self, mode: str = "normal") -> dict[str, Any]: ...

    def list_shares(self, payload: dict[str, Any]) -> list[Share]: ...

    def unlock(self, share_id: int, resource_id: int | None = None) -> UnlockResult: ...

    def rss(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def share(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def check_sharecode(self, share_code: str) -> dict[str, Any]: ...
