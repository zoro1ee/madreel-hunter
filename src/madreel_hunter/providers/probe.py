"""Endpoint / key probing that works **without** the SDK.

OpenAPI v2 validates in stages, and the stage where a request stops is
measurable without ever holding a valid envelope:

===================  ==============================================  ==========================
request              expected response                              conclusion
===================  ==============================================  ==========================
no key, plain body   ``400 openapi_codec_required``                  endpoint alive; key not parsed
bogus key + envelope ``401 openapi_key_invalid``                    baseline: rejected at key check
real key + envelope  ``401 openapi_codec_invalid (SDK identity...)`` key exists and is usable
===================  ==============================================  ==========================

A real key therefore proves itself by getting *past* the key check and failing
later at the sealed-SDK-identity step — while a fake key dies at the key check.
That is exactly what ``mh doctor`` reports.
"""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass, field

from ..http import Response, request

CODEC_REQUIRED = "openapi_codec_required"
KEY_INVALID = "openapi_key_invalid"
CODEC_INVALID = "openapi_codec_invalid"


@dataclass(slots=True)
class ProbeResult:
    base_url: str
    reachable: bool = False
    endpoint_status: int | None = None
    endpoint_code: str = ""
    key_state: str = "unknown"  # valid | invalid | unknown | not_configured
    key_code: str = ""
    key_message: str = ""
    baseline_code: str = ""
    sdk_installed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "reachable": self.reachable,
            "endpoint_status": self.endpoint_status,
            "endpoint_code": self.endpoint_code,
            "key_state": self.key_state,
            "key_code": self.key_code,
            "key_message": self.key_message,
            "baseline_code": self.baseline_code,
            "sdk_installed": self.sdk_installed,
            "notes": self.notes,
        }


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def dummy_envelope(kid: str) -> dict[str, object]:
    """A structurally valid envelope with a non-verifiable proof.

    Used only to reach the SDK identity / proof stage of the validation chain.
    It can never unlock data: the keys require the sealed SDK token.
    """
    return {
        "codec": "dian115-openapi-v2",
        "kid": kid,
        "developer_application_id": 0,
        "sdk_identity": "probe",
        "package_id": "dys_pkg_probe",
        "package_fingerprint": "dys_fp_probe",
        "nonce": _b64url(secrets.token_bytes(12)),
        "ts": int(time.time()),
        "payload": _b64url(b"{}"),
        "proof": _b64url(secrets.token_bytes(16)),
    }


def _post_me(base_url: str, body: object, key: str | None, *, timeout: float, proxy: str) -> Response:
    headers = {"X-OpenAPI-Key": key} if key else None
    return request(
        "POST",
        f"{base_url}/api/portal/openapi/me",
        json_body=body,
        headers=headers,
        timeout=timeout,
        proxy=proxy,
    )


def probe(base_url: str, api_key: str = "", *, timeout: float = 20.0, proxy: str = "") -> ProbeResult:
    """Run the three-stage probe and summarise what the portal says."""
    from .sdk import sdk_available  # local import keeps CLI startup cheap

    base = base_url.rstrip("/")
    result = ProbeResult(base_url=base, sdk_installed=sdk_available())

    # Stage 1 — endpoint liveness (no key, plain JSON body)
    try:
        resp = _post_me(base, {}, None, timeout=timeout, proxy=proxy)
    except ConnectionError as exc:
        result.notes.append(str(exc))
        return result

    result.endpoint_status = resp.status
    payload = resp.json() or {}
    result.endpoint_code = str(payload.get("code") or "")
    if resp.status in {200, 400, 401, 403, 404} and (result.endpoint_code or resp.status == 200):
        result.reachable = True
    else:
        result.notes.append(f"unexpected status {resp.status}: {resp.text[:160]}")
        return result

    if not api_key:
        result.key_state = "not_configured"
        return result

    # Stage 2 — baseline control: a bogus key must be rejected at the key check
    bogus = "dys_" + "0" * 64
    try:
        base_resp = _post_me(base, dummy_envelope(bogus[:8]), bogus, timeout=timeout, proxy=proxy)
        result.baseline_code = str((base_resp.json() or {}).get("code") or "")
    except ConnectionError as exc:  # pragma: no cover - network flake
        result.notes.append(str(exc))

    # Stage 3 — the real key
    try:
        real_resp = _post_me(base, dummy_envelope(api_key[:8]), api_key, timeout=timeout, proxy=proxy)
    except ConnectionError as exc:  # pragma: no cover
        result.notes.append(str(exc))
        return result

    payload = real_resp.json() or {}
    result.key_code = str(payload.get("code") or "")
    result.key_message = str(payload.get("msg") or "")
    result.key_state = "invalid" if result.key_code == KEY_INVALID else "valid"

    if result.key_state == "valid" and result.key_code == CODEC_INVALID:
        result.notes.append(
            "Key passed the key check and stopped at the sealed SDK identity step — "
            "this is the expected result for a valid key without the official SDK."
        )
    if result.key_state == "invalid":
        result.notes.append("The portal reports this key as invalid/disabled/deleted.")
    if not result.sdk_installed:
        result.notes.append(
            "Official SDK not installed: business calls (signin/list-shares/unlock/rss) "
            "require an approved developer application."
        )
    return result
