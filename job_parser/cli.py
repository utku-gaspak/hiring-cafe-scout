from __future__ import annotations

import argparse
import sys

from job_parser.app import run
from job_parser.branding import print_logo
from job_parser.config import SearchConfig, load_search_config, save_search_config
from job_parser.presets import (
    PRESETS_DIR,
    get_default_config,
    get_default_preset,
    list_all_presets,
    list_saved_presets,
)
from job_parser.wizard import collect_config


def main() -> None:
    print_logo()
    parser = build_parser()
    args = parser.parse_args()
    if args.list_presets:
        print_presets()
        return

    if args.config:
        base_config = load_search_config(args.config)
    elif args.preset:
        base_config = load_preset_config(args.preset)
    else:
        base_config = get_default_config()

    if args.interactive:
        config = collect_config(base_config)
    elif should_use_non_interactive_config(args):
        config = apply_args_to_config(base_config, args)
    else:
        config = resolve_interactive_start()

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
    parser.add_argument("--preset", help="Load a built-in or saved preset by slug.")
    parser.add_argument("--list-presets", action="store_true", help="List available presets and exit.")
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
            args.preset,
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


def resolve_interactive_start() -> SearchConfig:
    questionary = _load_questionary()
    style = questionary.Style(
        [
            ("qmark", "fg:#7aa2f7 bold"),
            ("question", "fg:#d8e6b5 bold"),
            ("answer", "fg:#9ece6a bold"),
            ("pointer", "fg:#f0b35a bold noreverse"),
            ("highlighted", "fg:#f0b35a bold noreverse"),
            ("selected", "fg:#f0b35a noreverse"),
            ("instruction", "fg:#7dcfff"),
            ("text", "fg:#d8e6b5"),
        ]
    )

    startup_choice = questionary.select(
        "Choose how to start",
        choices=[
            questionary.Choice(
                f"Use built-in preset: {get_default_preset().name}",
                value="builtin",
            ),
            questionary.Choice("Use saved preset", value="saved"),
            questionary.Choice("Create new search", value="new"),
        ],
        style=style,
        instruction="Use arrows to move, enter to continue",
    ).ask()
    if startup_choice is None:
        raise SystemExit(0)

    if startup_choice == "builtin":
        return choose_preset_action(get_default_config(), get_default_preset().name, style)
    if startup_choice == "saved":
        saved_presets = list_saved_presets()
        if not saved_presets:
            questionary.print(
                f"No saved presets found in `{PRESETS_DIR}/`. Starting a new search instead.",
                style="fg:#ff9e64",
            )
            return collect_config(build_fresh_search_config())
        preset_slug = questionary.select(
            "Saved presets",
            choices=[
                questionary.Choice(
                    f"{preset.name} ({preset.slug})",
                    value=preset.slug,
                )
                for preset in saved_presets.values()
            ],
            style=style,
            instruction="Use arrows to move, enter to continue",
        ).ask()
        if preset_slug is None:
            raise SystemExit(0)
        preset = saved_presets[preset_slug]
        return choose_preset_action(
            SearchConfig.from_dict(preset.config.to_dict()),
            preset.name,
            style,
        )
    return collect_config(build_fresh_search_config())


def choose_preset_action(config: SearchConfig, preset_name: str, style) -> SearchConfig:
    questionary = _load_questionary()
    action = questionary.select(
        f"{preset_name}",
        choices=[
            questionary.Choice("Run this preset now", value="run"),
            questionary.Choice("Edit this preset before running", value="edit"),
        ],
        style=style,
        instruction="Use arrows to move, enter to continue",
    ).ask()
    if action is None:
        raise SystemExit(0)
    if action == "run":
        return config
    return collect_config(config)


def load_preset_config(slug: str) -> SearchConfig:
    presets = list_all_presets()
    try:
        preset = presets[slug]
    except KeyError as exc:
        raise SystemExit(f"Unknown preset: {slug}") from exc
    return SearchConfig.from_dict(preset.config.to_dict())


def build_fresh_search_config() -> SearchConfig:
    return SearchConfig(
        keywords=[],
        departments=[],
        allowed_countries=[],
        cities=[],
        radius_km=None,
        radius_city="",
    )


def print_presets() -> None:
    presets = list_all_presets()
    for preset in presets.values():
        source = "built-in" if preset.builtin else "saved"
        print(f"{preset.slug} [{source}]")
        if preset.description:
            print(f"  {preset.description}")


def _load_questionary():
    try:
        import questionary
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: questionary\n"
            "Install it with `python3 -m pip install -r requirements.txt`."
        ) from exc
    return questionary
