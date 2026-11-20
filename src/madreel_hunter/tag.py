"""DT2 tag parsing.

MADREEL shares carry a pipe separated tag string, e.g.::

    DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|ATMOS|CHS|MUXED-SUB|MKV

The vocabulary below follows the tag groups exposed by the portal's
`share-fields` / `TAG` documentation. Unknown tokens are never dropped: they
land in ``Tag.other`` so that custom or newly introduced tags stay visible and
can be weighted through a scoring profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RESOLUTION_ALIASES: dict[str, str] = {
    "8K": "8K",
    "4320P": "8K",
    "4K": "4K",
    "2160P": "4K",
    "UHD": "4K",
    "1080P": "1080P",
    "1080I": "1080P",
    "720P": "720P",
    "576P": "576P",
    "480P": "480P",
}

SOURCE_ALIASES: dict[str, str] = {
    "BLURAY-REMUX": "BLURAY-REMUX",
    "BDREMUX": "BLURAY-REMUX",
    "REMUX": "REMUX",
    "BLURAY": "BLURAY",
    "BLU-RAY": "BLURAY",
    "WEB-DL": "WEB-DL",
    "WEBDL": "WEB-DL",
    "WEB": "WEB-DL",
    "WEBRIP": "WEBRIP",
    "HDTV": "HDTV",
    "HDTVRIP": "HDTV",
    "DVDRIP": "DVDRIP",
    "HDCAM": "HDCAM",
    "TC": "HDCAM",
}

VIDEO_CODECS: dict[str, str] = {
    "H.266": "H266",
    "H266": "H266",
    "VVC": "H266",
    "H.265": "HEVC",
    "H265": "HEVC",
    "HEVC": "HEVC",
    "X265": "HEVC",
    "H.264": "H264",
    "H264": "H264",
    "X264": "H264",
    "AVC": "H264",
    "AV1": "AV1",
    "VC-1": "VC1",
}

HDR_TAGS: tuple[str, ...] = ("DV", "DOVI", "DOLBYVISION", "HDR10+", "HDR10", "HDR", "HLG", "SDR")
AUDIO_PREFIXES: tuple[str, ...] = (
    "ATMOS",
    "TRUEHD",
    "DTS-HD",
    "DTS:X",
    "DTS",
    "DDP",
    "EAC3",
    "AC3",
    "DD+",
    "AAC",
    "FLAC",
    "LPCM",
    "OPUS",
)
SUBTITLE_TAGS: tuple[str, ...] = (
    "CHS",
    "CHT",
    "CHS&CHT",
    "CHT&CHS",
    "中字",
    "简中",
    "繁中",
    "简繁",
    "内嵌中文",
    "内封中文",
    "MUXED-SUB",
    "EXTERNAL-SUB",
)
BITDEPTH_TAGS: tuple[str, ...] = ("10BIT", "8BIT", "12BIT")
CONTAINER_TAGS: tuple[str, ...] = ("MKV", "MP4", "TS", "M2TS", "ISO", "AVI")
SDK_PREFIX = "DT2"


@dataclass(slots=True)
class Tag:
    """Structured representation of a DT2 tag string."""

    raw: str
    resolution: str | None = None
    source: str | None = None
    video_codec: str | None = None
    bit_depth: str | None = None
    hdr: list[str] = field(default_factory=list)
    audio: list[str] = field(default_factory=list)
    subtitles: list[str] = field(default_factory=list)
    container: str | None = None
    platform: str | None = None
    other: list[str] = field(default_factory=list)

    @property
    def has_chinese_subtitle(self) -> bool:
        for token in self.subtitles:
            upper = token.upper()
            if upper.startswith(("CHS", "CHT")) or "中" in token or "简" in token or "繁" in token:
                return True
        return False

    @property
    def is_dolby_vision(self) -> bool:
        return any(t in {"DV", "DOVI", "DOLBYVISION"} for t in self.hdr)

    def to_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "resolution": self.resolution,
            "source": self.source,
            "video_codec": self.video_codec,
            "bit_depth": self.bit_depth,
            "hdr": self.hdr,
            "audio": self.audio,
            "subtitles": self.subtitles,
            "container": self.container,
            "platform": self.platform,
            "other": self.other,
        }


def parse_tag(raw: str | None) -> Tag:
    """Parse a DT2 tag string into its components.

    >>> parse_tag("DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|ATMOS|CHS|MKV").resolution
    '4K'
    """
    tag = Tag(raw=raw or "")
    if not raw:
        return tag

    tokens = [t.strip() for t in raw.split("|") if t.strip()]
    for token in tokens:
        upper = token.upper()

        if upper == SDK_PREFIX:
            continue
        if upper in RESOLUTION_ALIASES:
            tag.resolution = tag.resolution or RESOLUTION_ALIASES[upper]
            continue
        if upper in SOURCE_ALIASES:
            tag.source = tag.source or SOURCE_ALIASES[upper]
            continue
        if upper in VIDEO_CODECS:
            tag.video_codec = tag.video_codec or VIDEO_CODECS[upper]
            continue
        if upper in BITDEPTH_TAGS:
            tag.bit_depth = tag.bit_depth or upper
            continue
        if upper in HDR_TAGS:
            tag.hdr.append("DV" if upper in {"DOVI", "DOLBYVISION"} else upper)
            continue
        if any(upper.startswith(prefix) for prefix in AUDIO_PREFIXES):
            tag.audio.append(token)
            continue
        if upper in {t.upper() for t in SUBTITLE_TAGS} or "字幕" in token:
            tag.subtitles.append(token)
            continue
        if upper in CONTAINER_TAGS:
            tag.container = tag.container or upper
            continue
        if upper.startswith("DYS_") or upper.startswith("DYS-"):
            tag.platform = tag.platform or token
            continue
        tag.other.append(token)

    if tag.platform is None:
        tag.platform = _guess_platform(tag.other)
        if tag.platform:
            tag.other = [t for t in tag.other if t != tag.platform]

    return tag


def _guess_platform(other: list[str]) -> str | None:
    """Streaming platform tags (NF, AMZN, DSNP ...) are short and uppercase."""
    for token in other:
        if 2 <= len(token) <= 6 and token.isupper() and token.isalpha():
            return token
    return None


def build_tag(**parts: str) -> str:
    """Compose a DT2 tag string from named components (used by `share` uploads)."""
    ordered = [
        SDK_PREFIX,
        parts.get("resolution", ""),
        parts.get("source", ""),
        parts.get("platform", ""),
        parts.get("video_codec", ""),
        parts.get("bit_depth", ""),
        parts.get("hdr", ""),
        parts.get("audio", ""),
        parts.get("subtitles", ""),
        parts.get("container", ""),
    ]
    return "|".join(p for p in ordered if p)
