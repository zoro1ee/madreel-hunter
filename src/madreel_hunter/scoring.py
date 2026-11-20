"""Share scoring.

The portal only tells you *which* shares exist; picking the best one is the
client's job (see "工具对接建议" in the official docs). This module implements a
transparent, configurable scoring profile so the ranking is explainable instead
of being a black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Share
from .tag import Tag, parse_tag

DEFAULT_PROFILE: dict[str, Any] = {
    "resolution": {
        "8K": 90,
        "4K": 80,
        "1080P": 60,
        "720P": 40,
        "576P": 20,
        "480P": 10,
    },
    "source": {
        "BLURAY-REMUX": 40,
        "REMUX": 38,
        "WEB-DL": 30,
        "BLURAY": 26,
        "WEBRIP": 18,
        "HDTV": 10,
        "DVDRIP": 4,
        "HDCAM": 0,
    },
    "hdr": {
        "DV": 16,
        "HDR10+": 12,
        "HDR10": 8,
        "HDR": 6,
        "HLG": 4,
    },
    "audio": {
        "ATMOS": 10,
        "TRUEHD": 8,
        "DTS:X": 8,
        "DTS-HD": 6,
        "DDP": 4,
        "EAC3": 3,
        "AC3": 2,
        "AAC": 1,
    },
    "chinese_subtitle_bonus": 10,
    "use_count_cap": 20,
    "offline_penalty": 8,
    "unlocked_bonus": 0,
}

RESOLUTION_RANK = {"480P": 0, "576P": 1, "720P": 2, "1080P": 3, "4K": 4, "8K": 5}


@dataclass(slots=True)
class ScoredShare:
    share: Share
    score: float
    tag: Tag
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "share_id": self.share.share_id,
            "resource_id": self.share.resource_id,
            "score": round(self.score, 1),
            "reasons": self.reasons,
            "tag": self.tag.to_dict(),
        }


def score_share(share: Share, profile: dict[str, Any] | None = None) -> ScoredShare:
    """Score one share against a scoring profile."""
    prof = {**DEFAULT_PROFILE, **(profile or {})}
    tag = parse_tag(share.tag or str(share.raw.get("quality") or ""))
    reasons: list[str] = []
    score = 0.0

    if tag.resolution and tag.resolution in prof["resolution"]:
        points = prof["resolution"][tag.resolution]
        score += points
        reasons.append(f"resolution:{tag.resolution} +{points}")

    if tag.source and tag.source in prof["source"]:
        points = prof["source"][tag.source]
        score += points
        reasons.append(f"source:{tag.source} +{points}")

    for hdr in tag.hdr:
        points = prof["hdr"].get(hdr)
        if points:
            score += points
            reasons.append(f"hdr:{hdr} +{points}")

    for track in tag.audio:
        for key, points in prof["audio"].items():
            if track.upper().startswith(key):
                score += points
                reasons.append(f"audio:{track} +{points}")
                break

    if share.has_chinese_subtitle or tag.has_chinese_subtitle:
        bonus = prof["chinese_subtitle_bonus"]
        score += bonus
        reasons.append(f"chinese-subtitle +{bonus}")

    if share.use_count:
        points = min(share.use_count, int(prof["use_count_cap"]))
        if points:
            score += points
            reasons.append(f"hot:{share.use_count} +{points}")

    if share.share_kind == "offline" and prof["offline_penalty"]:
        points = prof["offline_penalty"]
        score -= points
        reasons.append(f"offline -{points}")

    if share.unlocked and prof["unlocked_bonus"]:
        score += prof["unlocked_bonus"]
        reasons.append(f"already-unlocked +{prof['unlocked_bonus']}")

    return ScoredShare(share=share, score=score, tag=tag, reasons=reasons)


def rank(
    shares: list[Share],
    profile: dict[str, Any] | None = None,
    *,
    min_resolution: str | None = None,
    require_chinese_sub: bool = False,
    max_share_kind: str | None = None,
) -> list[ScoredShare]:
    """Score and rank shares, applying hard filters first."""
    scored: list[ScoredShare] = []
    for share in shares:
        item = score_share(share, profile)
        if min_resolution:
            have = RESOLUTION_RANK.get(item.tag.resolution or "", -1)
            want = RESOLUTION_RANK.get(min_resolution.upper(), 99)
            if have < want:
                continue
        if require_chinese_sub and not (item.share.has_chinese_subtitle or item.tag.has_chinese_subtitle):
            continue
        if max_share_kind and item.share.share_kind and item.share.share_kind != max_share_kind:
            continue
        scored.append(item)

    scored.sort(key=lambda s: (-s.score, s.share.share_id))
    return scored
