"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import Config, ConfigError, load_config
from .models import Share
from .providers import OpenApiError, ProbeResult, SdkNotInstalled, SdkProvider, probe, sdk_available
from .scoring import ScoredShare, rank
from .tag import parse_tag
from .targets import post_webhook, write_json
from .tmdb import TmdbClient, TmdbError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEEDS_SDK = 2


# --------------------------------------------------------------------------- helpers


def _human_size(size: int | None) -> str:
    if not size:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return "-"


def _print_table(rows: list[ScoredShare]) -> None:
    if not rows:
        print("no candidate shares matched the filters")
        return
    header = f"{'#':>3}  {'share_id':>9}  {'score':>6}  {'res':>5}  {'source':>12}  {'size':>8}  {'sub':>3}  key tags"
    print(header)
    print("-" * len(header))
    for index, item in enumerate(rows, start=1):
        tag = item.tag
        extras = "/".join(
            part for part in [*(tag.hdr or []), *(tag.audio[:1] or []), tag.video_codec or ""] if part
        )
        sub = "yes" if (item.share.has_chinese_subtitle or tag.has_chinese_subtitle) else "-"
        print(
            f"{index:>3}  {item.share.share_id:>9}  {item.score:>6.1f}  "
            f"{(tag.resolution or '-'):>5}  {(tag.source or '-'):>12}  "
            f"{_human_size(item.share.size_bytes):>8}  {sub:>3}  {extras}"
        )


def _provider(config: Config):
    return SdkProvider(config)


# --------------------------------------------------------------------------- commands


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result: ProbeResult = probe(
        args.base_url or config.base_url,
        config.api_key,
        timeout=args.timeout or config.timeout,
        proxy=config.proxy,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return EXIT_OK

    print(f"base_url        : {result.base_url}")
    print(f"endpoint alive  : {'yes' if result.reachable else 'NO'} ({result.endpoint_code or 'n/a'})")
    print(f"official SDK    : {'installed' if result.sdk_installed else 'not installed'}")
    if result.key_state == "not_configured":
        print("api key         : not configured (set MADREEL_API_KEY)")
    else:
        state = "VALID" if result.key_state == "valid" else result.key_state.upper()
        print(f"api key         : {state}  [{result.key_code or 'n/a'}] {result.key_message}")
        print(f"control (bogus) : {result.baseline_code or 'n/a'}")
    for note in result.notes:
        print(f"note            : {note}")
    return EXIT_OK


def cmd_tmdb(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = TmdbClient(config.tmdb_api_key, timeout=config.timeout, proxy=config.proxy)
    matches = client.search(args.query, media_type=args.type, year=args.year)[: args.limit]
    if args.json:
        print(json.dumps([m.__dict__ for m in matches], ensure_ascii=False, indent=2))
        return EXIT_OK
    if not matches:
        print("no TMDB match")
        return EXIT_OK
    for match in matches:
        print(f"{match.tmdb_id:>9}  {match.media_type:<5}  {match.year or '----'}  {match.title}")
    return EXIT_OK


def cmd_tag(args: argparse.Namespace) -> int:
    tag = parse_tag(args.tag)
    data = tag.to_dict()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return EXIT_OK
    for key, value in data.items():
        print(f"{key:<12}: {value}")
    return EXIT_OK


def cmd_hunt(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    tmdb_id = args.tmdb_id
    media_type = args.media_type or "movie"
    if not tmdb_id:
        if not args.query:
            print("specify --query or --tmdb-id", file=sys.stderr)
            return EXIT_ERROR
        client = TmdbClient(config.tmdb_api_key, timeout=config.timeout, proxy=config.proxy)
        matches = client.search(args.query, media_type=args.type)
        if not matches:
            print(f"TMDB has no match for {args.query!r}", file=sys.stderr)
            return EXIT_ERROR
        best = matches[0]
        tmdb_id, media_type = best.tmdb_id, best.media_type
        print(f"tmdb: {best.title} ({best.year}) -> {tmdb_id}/{media_type}")

    if not sdk_available():
        print(
            "OpenAPI v2 business calls need the official SDK (sealed identity + "
            "derived keys). Run `mh doctor` to check your key, and apply for a "
            "developer application at https://madow.tv/openapiv2.",
            file=sys.stderr,
        )
        return EXIT_NEEDS_SDK

    provider = _provider(config)
    payload: dict[str, Any] = {"tmdb_id": tmdb_id, "media_type": media_type, "size": args.limit}
    if args.season is not None:
        payload["season"] = args.season
    shares: list[Share] = provider.list_shares(payload)

    ranked = rank(
        shares,
        config.scoring,
        min_resolution=args.min_res,
        require_chinese_sub=args.chinese_sub,
        max_share_kind=args.share_kind,
    )
    _print_table(ranked)

    chosen = ranked[:1] if args.only_best else ranked
    if args.out and ranked:
        write_json(args.out, [item.to_dict() for item in ranked])
        print(f"written: {args.out}")

    if args.unlock and chosen:
        results = []
        for item in chosen:
            try:
                unlocked = provider.unlock(item.share.share_id, item.share.resource_id)
            except OpenApiError as exc:
                print(f"unlock failed for {item.share.share_id}: {exc}", file=sys.stderr)
                continue
            results.append(unlocked)
            print(f"unlocked {item.share.share_id}: {unlocked.share_url} (code: {unlocked.password or '-'})")
        if args.webhook and results:
            payload = {
                "source": "madreel-hunter",
                "tmdb_id": tmdb_id,
                "media_type": media_type,
                "items": [
                    {
                        "share_id": r.share_id,
                        "share_url": r.share_url,
                        "password": r.password,
                        "kind": r.kind,
                    }
                    for r in results
                ],
            }
            status = post_webhook(
                args.webhook,
                payload,
                token=args.webhook_token,
                proxy=config.proxy,
            )
            print(f"webhook: HTTP {status}")
    return EXIT_OK


def cmd_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"source      : {config.source_path or 'environment only'}")
    print(f"base_url    : {config.base_url}")
    print(f"api key kid : {config.kid or '(not set)'}  (full value never printed)")
    print(f"tmdb key    : {'set' if config.tmdb_api_key else 'not set'}")
    print(f"scoring     : {json.dumps(config.scoring, ensure_ascii=False) if config.scoring else 'default profile'}")
    return EXIT_OK


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mh",
        description="TMDB-driven 115 share matching, scoring and unlock automation for MADREEL OpenAPI v2.",
    )
    parser.add_argument("--version", action="version", version=f"madreel-hunter {__version__}")
    parser.add_argument("--config", help="path to config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="probe endpoint + key validity without the SDK")
    doctor.add_argument("--base-url")
    doctor.add_argument("--timeout", type=float)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    tmdb = sub.add_parser("tmdb", help="TMDB lookups")
    tmdb_sub = tmdb.add_subparsers(dest="tmdb_command", required=True)
    search = tmdb_sub.add_parser("search", help="search a title and print tmdb_id candidates")
    search.add_argument("query")
    search.add_argument("--type", default="multi", choices=["multi", "movie", "tv"])
    search.add_argument("--year", type=int)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_tmdb)

    tag = sub.add_parser("tag", help="DT2 tag utilities")
    tag_sub = tag.add_subparsers(dest="tag_command", required=True)
    parse = tag_sub.add_parser("parse", help="parse a DT2 tag string")
    parse.add_argument("tag")
    parse.add_argument("--json", action="store_true")
    parse.set_defaults(func=cmd_tag)

    hunt = sub.add_parser("hunt", help="list, rank and optionally unlock shares for one title")
    target = hunt.add_mutually_exclusive_group(required=True)
    target.add_argument("--query", help="title to resolve through TMDB")
    target.add_argument("--tmdb-id", type=int)
    hunt.add_argument("--type", default="multi", choices=["multi", "movie", "tv"], help="TMDB search type")
    hunt.add_argument("--media-type", choices=["movie", "tv"], help="portal media type")
    hunt.add_argument("--season", type=int)
    hunt.add_argument("--min-res", choices=["720P", "1080P", "4K", "8K"])
    hunt.add_argument("--chinese-sub", action="store_true", help="keep only shares with Chinese subtitles")
    hunt.add_argument("--share-kind", choices=["115", "offline"])
    hunt.add_argument("--limit", type=int, default=50)
    hunt.add_argument("--only-best", action="store_true", help="unlock only the top-ranked share")
    hunt.add_argument("--unlock", action="store_true", help="unlock the selected shares")
    hunt.add_argument("--out", help="write ranked candidates to a JSON file")
    hunt.add_argument("--webhook", help="POST unlock results to this URL")
    hunt.add_argument("--webhook-token", default="")
    hunt.set_defaults(func=cmd_hunt)

    config_cmd = sub.add_parser("config", help="show effective configuration")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    show = config_sub.add_parser("show")
    show.set_defaults(func=cmd_config)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except SdkNotInstalled as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_NEEDS_SDK
    except (OpenApiError, TmdbError, ConnectionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
