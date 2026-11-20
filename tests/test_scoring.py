from madreel_hunter.models import Share
from madreel_hunter.scoring import rank, score_share


def make_share(share_id: int, tag: str, **kwargs) -> Share:
    return Share(share_id=share_id, tag=tag, **kwargs)


def test_4k_beats_1080p():
    four_k = make_share(1, "DT2|4K|WEB-DL|NF|HEVC|10BIT|DDP5.1|CHS|MKV")
    full_hd = make_share(2, "DT2|1080P|WEB-DL|NF|HEVC|10BIT|DDP5.1|CHS|MKV")
    assert score_share(four_k).score > score_share(full_hd).score


def test_remux_beats_webdl_at_same_resolution():
    remux = make_share(1, "DT2|4K|BLURAY-REMUX|HEVC|10BIT|DV|DTS-HD|CHS|MKV")
    webdl = make_share(2, "DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|CHS|MKV")
    assert score_share(remux).score > score_share(webdl).score


def test_chinese_subtitle_bonus():
    with_sub = make_share(1, "DT2|4K|WEB-DL|HEVC|CHS|MKV")
    without_sub = make_share(2, "DT2|4K|WEB-DL|HEVC|MKV")
    assert score_share(with_sub).score > score_share(without_sub).score


def test_offline_penalty():
    online = make_share(1, "DT2|4K|WEB-DL|HEVC|CHS|MKV", share_kind="115")
    offline = make_share(2, "DT2|4K|WEB-DL|HEVC|CHS|MKV", share_kind="offline")
    assert score_share(online).score > score_share(offline).score


def test_popularity_is_capped():
    hot = make_share(1, "DT2|4K|WEB-DL|HEVC|CHS|MKV", use_count=10_000)
    warm = make_share(2, "DT2|4K|WEB-DL|HEVC|CHS|MKV", use_count=50)
    cold = make_share(3, "DT2|4K|WEB-DL|HEVC|CHS|MKV", use_count=20)
    # anything above the cap scores the same
    assert score_share(hot).score == score_share(warm).score
    assert score_share(warm).score - score_share(cold).score == 0
    low = make_share(4, "DT2|4K|WEB-DL|HEVC|CHS|MKV", use_count=5)
    assert 0 < score_share(cold).score - score_share(low).score <= 20


def test_rank_orders_and_filters():
    shares = [
        make_share(1, "DT2|1080P|WEB-DL|HEVC|CHS|MKV"),
        make_share(2, "DT2|4K|WEB-DL|NF|HEVC|DV|CHS|MKV", use_count=5),
        make_share(3, "DT2|720P|HDTV|H264|MKV"),
    ]
    ordered = rank(shares)
    assert [item.share.share_id for item in ordered][0] == 2

    only_4k = rank(shares, min_resolution="4K")
    assert [item.share.share_id for item in only_4k] == [2]

    only_sub = rank(shares, require_chinese_sub=True)
    assert 3 not in [item.share.share_id for item in only_sub]


def test_custom_profile_weights():
    share = make_share(1, "DT2|4K|WEB-DL|HEVC|MKV")
    default_score = score_share(share).score
    heavy = score_share(share, {"resolution": {"4K": 200}}).score
    assert heavy > default_score
