from __future__ import annotations

from job_parser.config import CITY_COORDS, SearchConfig


WORKPLACE_OPTIONS = ["Remote", "Hybrid", "Onsite"]
COMMITMENT_OPTIONS = ["Full Time", "Part Time", "Contract"]
SENIORITY_OPTIONS = ["Entry", "Junior", "Associate", "Intern", "Graduate", "Unspecified"]
REMOTE_SCOPE_OPTIONS = ["Europe", "Worldwide"]
OUTPUT_OPTIONS = ["Markdown", "JSON"]
COUNTRY_SCOPE_OPTIONS = ["Germany only", "Custom country codes"]
LOCATION_MODES = [
    "No city filter",
    "Select common cities",
    "Enter custom city names",
    "Use radius filter",
]


def collect_config(defaults: SearchConfig | None = None) -> SearchConfig:
    base = defaults or SearchConfig()
    questionary = _load_questionary()
    style = questionary.Style(
        [
            ("qmark", "fg:#7aa2f7 bold"),
            ("question", "bold"),
            ("answer", "fg:#9ece6a bold"),
            ("pointer", "fg:#ff9e64 bold"),
            ("highlighted", "fg:#ff9e64 bold"),
            ("selected", "fg:#9ece6a"),
            ("separator", "fg:#565f89"),
            ("instruction", "fg:#7dcfff"),
            ("text", ""),
        ]
    )

    keywords = prompt_keyword_editor(questionary, style, base.keywords)
    workplace_types = prompt_checkbox(
        questionary,
        style,
        "Workplace types",
        WORKPLACE_OPTIONS,
        base.workplace_types,
    )
    allowed_countries = prompt_country_scope(questionary, style, base.allowed_countries)
    location_mode = prompt_select(
        questionary,
        style,
        "Location filter",
        LOCATION_MODES,
        _default_location_mode(base),
    )
    cities, radius_city, radius_km = prompt_location_details(
        questionary,
        style,
        base,
        location_mode,
    )
    seniority_labels = prompt_checkbox(
        questionary,
        style,
        "Seniority filters",
        SENIORITY_OPTIONS,
        _default_seniority_labels(base),
    )
    commitments = prompt_checkbox(
        questionary,
        style,
        "Commitment filters",
        COMMITMENT_OPTIONS,
        base.commitments,
    )
    remote_scopes = prompt_checkbox(
        questionary,
        style,
        "Remote scopes",
        REMOTE_SCOPE_OPTIONS,
        base.remote_scopes,
        allow_empty=True,
    )
    outputs = prompt_checkbox(
        questionary,
        style,
        "Output formats",
        OUTPUT_OPTIONS,
        _default_outputs(base),
    )
    markdown_output = questionary.text(
        "Markdown output path",
        default=base.markdown_output,
        style=style,
    ).ask()
    json_output = questionary.text(
        "JSON output path",
        default=base.json_output,
        style=style,
    ).ask()
    max_pages = prompt_max_pages(questionary, style, base.max_pages)
    include_seen = questionary.confirm(
        "Include previously seen jobs?",
        default=base.include_seen,
        style=style,
    ).ask()

    config = SearchConfig(
        keywords=keywords,
        workplace_types=workplace_types,
        allowed_countries=allowed_countries,
        remote_scopes=remote_scopes,
        seniority_terms=[label.lower() for label in seniority_labels if label != "Unspecified"],
        include_unspecified_seniority="Unspecified" in seniority_labels,
        commitments=commitments,
        base_url=base.base_url,
        markdown_output=markdown_output or base.markdown_output,
        json_output=json_output or base.json_output,
        export_markdown="Markdown" in outputs,
        export_json="JSON" in outputs,
        seen_ids_file=base.seen_ids_file,
        include_seen=bool(include_seen),
        max_pages=max_pages,
        cities=cities,
        radius_km=radius_km,
        radius_city=radius_city,
    )

    if not questionary.confirm(
        f"{render_summary(config)}\n\nStart scraping with these settings?",
        default=True,
        style=style,
    ).ask():
        raise SystemExit(0)

    return config


def render_summary(config: SearchConfig) -> str:
    location_detail = "All matching countries"
    if config.cities:
        location_detail = f"Cities: {', '.join(config.cities)}"
    elif config.radius_km and config.radius_city:
        location_detail = f"Radius: {config.radius_km} km around {config.radius_city}"

    outputs = []
    if config.export_markdown:
        outputs.append("Markdown")
    if config.export_json:
        outputs.append("JSON")

    lines = [
        f"Keywords: {', '.join(config.keywords)}",
        f"Workplace types: {', '.join(config.workplace_types)}",
        f"Countries: {', '.join(config.allowed_countries)}",
        location_detail,
        f"Seniority: {', '.join(config.seniority_terms) or 'none'}"
        + (" + unspecified" if config.include_unspecified_seniority else ""),
        f"Commitments: {', '.join(config.commitments)}",
        f"Remote scopes: {', '.join(config.remote_scopes) or 'none'}",
        f"Outputs: {', '.join(outputs)}",
        f"Max pages: {config.max_pages if config.max_pages is not None else 'unlimited'}",
        f"Include seen jobs: {'yes' if config.include_seen else 'no'}",
    ]
    return "\n".join(lines)


def prompt_keyword_editor(questionary, style, default_keywords: list[str]) -> list[str]:
    keywords = list(default_keywords)
    while True:
        action = questionary.select(
            "Keywords",
            choices=[
                questionary.Choice(f"Edit selected keywords ({', '.join(keywords)})", value="edit"),
                questionary.Choice("Add another keyword", value="add"),
                questionary.Choice("Continue", value="continue"),
            ],
            style=style,
            instruction="Use arrows to move, enter to continue",
        ).ask()
        if action == "edit":
            selected = prompt_checkbox(
                questionary,
                style,
                "Toggle the keywords you want to keep",
                keywords,
                keywords,
            )
            if selected:
                keywords = selected
            else:
                questionary.print("Keep at least one keyword selected.", style="fg:#f7768e")
        elif action == "add":
            new_keyword = questionary.text(
                "New keyword",
                style=style,
                validate=lambda value: bool(value.strip()) or "Enter a keyword.",
            ).ask()
            if new_keyword is None:
                raise SystemExit(0)
            normalized = {keyword.casefold() for keyword in keywords}
            if new_keyword.strip().casefold() not in normalized:
                keywords.append(new_keyword.strip())
        else:
            return keywords


def prompt_country_scope(questionary, style, default_countries: list[str]) -> list[str]:
    scope = prompt_select(
        questionary,
        style,
        "Country scope",
        COUNTRY_SCOPE_OPTIONS,
        "Germany only" if default_countries == ["DE"] else "Custom country codes",
    )
    if scope == "Germany only":
        return ["DE"]

    countries = questionary.text(
        "Custom ISO country codes",
        default=",".join(default_countries),
        style=style,
        validate=lambda value: bool(csv_values(value)) or "Enter at least one country code.",
    ).ask()
    if countries is None:
        raise SystemExit(0)
    return [value.upper() for value in csv_values(countries)]


def prompt_location_details(questionary, style, base: SearchConfig, location_mode: str) -> tuple[list[str], str, int | None]:
    if location_mode == "No city filter":
        return [], "", None
    if location_mode == "Select common cities":
        cities = prompt_checkbox(
            questionary,
            style,
            "Select common cities",
            list(CITY_COORDS.keys()),
            [city for city in base.cities if city in CITY_COORDS],
        )
        return cities, "", None
    if location_mode == "Enter custom city names":
        cities = questionary.text(
            "Custom city names",
            default=",".join([city for city in base.cities if city not in CITY_COORDS]),
            style=style,
            validate=lambda value: bool(csv_values(value)) or "Enter at least one city.",
        ).ask()
        if cities is None:
            raise SystemExit(0)
        return csv_values(cities), "", None

    radius_city = prompt_select(
        questionary,
        style,
        "Radius center city",
        list(CITY_COORDS.keys()),
        base.radius_city if base.radius_city in CITY_COORDS else "Berlin",
    )
    radius_raw = questionary.text(
        "Radius in km",
        default=str(base.radius_km or 50),
        style=style,
        validate=lambda value: value.isdigit() and int(value) > 0 or "Enter a positive integer.",
    ).ask()
    if radius_raw is None:
        raise SystemExit(0)
    return [], radius_city, int(radius_raw)


def prompt_max_pages(questionary, style, default_value: int | None) -> int | None:
    default_text = "" if default_value is None else str(default_value)
    value = questionary.text(
        "Max pages to scrape (0 for unlimited)",
        default=default_text,
        style=style,
        validate=lambda raw: raw == "" or raw == "0" or (raw.isdigit() and int(raw) > 0) or "Enter blank, 0, or a positive integer.",
    ).ask()
    if value is None:
        raise SystemExit(0)
    if value == "":
        return default_value
    if value == "0":
        return None
    return int(value)


def prompt_checkbox(questionary, style, title: str, options: list[str], default: list[str], allow_empty: bool = False) -> list[str]:
    while True:
        result = questionary.checkbox(
            title,
            choices=[questionary.Choice(option, checked=option in default) for option in options],
            validate=lambda values: allow_empty or bool(values) or "Select at least one option.",
            style=style,
            instruction="Use arrows to move, space to toggle, enter to continue",
        ).ask()
        if result is None:
            raise SystemExit(0)
        if result or allow_empty:
            return list(result)


def prompt_select(questionary, style, title: str, options: list[str], default: str) -> str:
    result = questionary.select(
        title,
        choices=options,
        default=default,
        style=style,
        instruction="Use arrows to move, enter to continue",
    ).ask()
    if result is None:
        raise SystemExit(0)
    return str(result)


def csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _default_seniority_labels(config: SearchConfig) -> list[str]:
    labels = [term.capitalize() for term in config.seniority_terms]
    if config.include_unspecified_seniority:
        labels.append("Unspecified")
    return labels


def _default_outputs(config: SearchConfig) -> list[str]:
    outputs: list[str] = []
    if config.export_markdown:
        outputs.append("Markdown")
    if config.export_json:
        outputs.append("JSON")
    return outputs


def _default_location_mode(config: SearchConfig) -> str:
    if config.radius_km and config.radius_city:
        return "Use radius filter"
    if config.cities:
        if any(city in CITY_COORDS for city in config.cities):
            return "Select common cities"
        return "Enter custom city names"
    return "No city filter"


def _load_questionary():
    try:
        import questionary
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: questionary\n"
            "Install it with `python3 -m pip install -r requirements.txt`."
        ) from exc
    return questionary
