"""Data models shared across the CLI, providers and targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Share:
    """A single unlockable share returned by `list-shares` / `rss`."""

    share_id: int
    resource_id: int | None = None
    tmdb_id: int | None = None
    media_type: str | None = None
    season: int | None = None
    tag: str = ""
    size_bytes: int | None = None
    share_kind: str | None = None  # "115" | "offline"
    has_chinese_subtitle: bool = False
    unlocked: bool = False
    use_count: int = 0
    created_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Share":
        return cls(
            share_id=int(payload.get("share_id") or 0),
            resource_id=_as_int(payload.get("resource_id")),
            tmdb_id=_as_int(payload.get("tmdb_id")),
            media_type=payload.get("media_type"),
            season=_as_int(payload.get("season")),
            tag=str(payload.get("tag") or payload.get("quality") or ""),
            size_bytes=_as_int(payload.get("size_bytes") or payload.get("total_size_bytes")),
            share_kind=payload.get("share_kind"),
            has_chinese_subtitle=bool(payload.get("has_chinese_subtitle")),
            unlocked=bool(payload.get("unlocked")),
            use_count=int(payload.get("use_count") or 0),
            created_at=payload.get("created_at"),
            raw=payload,
        )


@dataclass(slots=True)
class UnlockResult:
    """Result of an `unlock` call: the 115 link and extraction code."""

    share_id: int
    resource_id: int | None = None
    share_url: str | None = None
    password: str | None = None
    kind: str | None = None  # "115" | "offline"
    created_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TmdbMatch:
    tmdb_id: int
    media_type: str
    title: str
    year: str | None
    overview: str = ""
    popularity: float = 0.0


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
