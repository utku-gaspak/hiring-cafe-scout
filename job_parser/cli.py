from __future__ import annotations

import argparse
import sys

from job_parser.app import run
from job_parser.config import SearchConfig, load_search_config, save_search_config
from job_parser.wizard import collect_config


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    base_config = load_search_config(args.config) if args.config else SearchConfig()

    if args.interactive:
        config = collect_config(base_config)
    elif should_use_non_interactive_config(args):
        config = apply_args_to_config(base_config, args)
    else:
        config = collect_config(base_config)

    if args.save_config:
        save_search_config(args.save_config, config)
        print(f"Saved config → {args.save_config}")
        if args.save_config_only:
            return

    import asyncio

    asyncio.run(run(config))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape hiring.cafe job listings.")
    parser.add_argument("--interactive", action="store_true", help="Force the interactive setup wizard.")
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Run from flags and/or config without the interactive setup wizard.",
    )
    parser.add_argument("--config", help="Load search settings from a JSON config file.")
    parser.add_argument("--save-config", help="Write the resolved search settings to a JSON config file.")
    parser.add_argument(
        "--save-config-only",
        action="store_true",
        help="Save the resolved config and exit without scraping.",
    )
    parser.add_argument("--keywords", help="Comma-separated keywords.")
    parser.add_argument("--workplace-types", help="Comma-separated workplace types.")
    parser.add_argument("--countries", help="Comma-separated ISO country codes.")
    parser.add_argument("--cities", help="Comma-separated city filters.")
    parser.add_argument("--radius-city", help="Radius center city.")
    parser.add_argument("--radius-km", type=int, help="Radius in kilometers.")
    parser.add_argument("--remote-scopes", help="Comma-separated remote scopes.")
    parser.add_argument("--seniority-terms", help="Comma-separated seniority terms.")
    parser.add_argument(
        "--no-unspecified-seniority",
        action="store_true",
        help="Exclude jobs with blank seniority.",
    )
    parser.add_argument("--commitments", help="Comma-separated commitment filters.")
    parser.add_argument("--max-pages", type=int, help="Maximum pages to scrape. Use 0 for unlimited.")
    parser.add_argument("--include-seen", action="store_true", help="Include jobs already present in seen_ids.txt.")
    parser.add_argument("--markdown-output", help="Markdown output file path.")
    parser.add_argument("--json-output", help="JSON output file path.")
    parser.add_argument("--no-markdown", action="store_true", help="Disable markdown output.")
    parser.add_argument("--no-json", action="store_true", help="Disable JSON output.")
    return parser


def should_use_non_interactive_config(args: argparse.Namespace) -> bool:
    return (
        args.no_interactive
        or args.config is not None
        or has_cli_overrides(args)
        or not sys.stdin.isatty()
    )


def has_cli_overrides(args: argparse.Namespace) -> bool:
    return any(
        value
        for value in [
            args.keywords,
            args.workplace_types,
            args.countries,
            args.cities,
            args.radius_city,
            args.radius_km is not None,
            args.remote_scopes,
            args.seniority_terms,
            args.no_unspecified_seniority,
            args.commitments,
            args.max_pages is not None,
            args.include_seen,
            args.markdown_output,
            args.json_output,
            args.no_markdown,
            args.no_json,
            args.save_config,
            args.save_config_only,
        ]
    )


def apply_args_to_config(base: SearchConfig, args: argparse.Namespace) -> SearchConfig:
    config = SearchConfig.from_dict(base.to_dict())

    if args.keywords:
        config.keywords = parse_csv(args.keywords)
    if args.workplace_types:
        config.workplace_types = parse_csv(args.workplace_types)
    if args.countries:
        config.allowed_countries = [value.upper() for value in parse_csv(args.countries)]
    if args.cities:
        config.cities = parse_csv(args.cities)
        config.radius_city = ""
        config.radius_km = None
    if args.radius_city is not None:
        config.radius_city = args.radius_city
        config.cities = []
    if args.radius_km is not None:
        config.radius_km = None if args.radius_km == 0 else args.radius_km
    if args.remote_scopes:
        config.remote_scopes = parse_csv(args.remote_scopes)
    if args.seniority_terms:
        config.seniority_terms = [value.lower() for value in parse_csv(args.seniority_terms)]
    if args.no_unspecified_seniority:
        config.include_unspecified_seniority = False
    if args.commitments:
        config.commitments = parse_csv(args.commitments)
    if args.max_pages is not None:
        config.max_pages = None if args.max_pages == 0 else args.max_pages
    if args.include_seen:
        config.include_seen = True
    if args.markdown_output:
        config.markdown_output = args.markdown_output
    if args.json_output:
        config.json_output = args.json_output
    if args.no_markdown:
        config.export_markdown = False
    if args.no_json:
        config.export_json = False

    if not config.export_markdown and not config.export_json:
        raise SystemExit("At least one output format must remain enabled.")

    return config


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
