from madreel_hunter.tag import build_tag, parse_tag


FULL_TAG = "DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|ATMOS|CHS|MUXED-SUB|MKV"


def test_parse_full_tag():
    tag = parse_tag(FULL_TAG)
    assert tag.resolution == "4K"
    assert tag.source == "WEB-DL"
    assert tag.video_codec == "HEVC"
    assert tag.bit_depth == "10BIT"
    assert "DV" in tag.hdr
    assert any(a.startswith("DDP") for a in tag.audio)
    assert "ATMOS" in " ".join(tag.audio).upper() or "ATMOS" in tag.other
    assert tag.container == "MKV"
    assert tag.platform == "NF"
    assert tag.has_chinese_subtitle is True
    assert tag.is_dolby_vision is True


def test_parse_remux_1080p_without_subtitle():
    tag = parse_tag("DT2|1080P|BLURAY-REMUX|AMZN|H264|8BIT|HDR10|TRUEHD|CHT|MP4")
    assert tag.resolution == "1080P"
    assert tag.source == "BLURAY-REMUX"
    assert tag.video_codec == "H264"
    assert tag.container == "MP4"
    assert tag.platform == "AMZN"
    # CHT counts as a Chinese subtitle track
    assert tag.has_chinese_subtitle is True


def test_unknown_tokens_are_kept():
    tag = parse_tag("DT2|4K|WEB-DL|SOMETHINGNEW|MKV")
    assert "SOMETHINGNEW" in tag.other


def test_alias_normalisation():
    assert parse_tag("2160P").resolution == "4K"
    assert parse_tag("H.265").video_codec == "HEVC"
    assert parse_tag("WEBDL").source == "WEB-DL"


def test_empty_tag():
    tag = parse_tag("")
    assert tag.resolution is None
    assert tag.has_chinese_subtitle is False


def test_build_tag_round_trip():
    composed = build_tag(
        resolution="4K",
        source="WEB-DL",
        platform="NF",
        video_codec="HEVC",
        bit_depth="10BIT",
        hdr="DV",
        audio="DDP5.1",
        subtitles="CHS",
        container="MKV",
    )
    assert composed.startswith("DT2|")
    parsed = parse_tag(composed)
    assert parsed.resolution == "4K"
    assert parsed.source == "WEB-DL"
