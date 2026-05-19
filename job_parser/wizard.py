from __future__ import annotations

from job_parser.config import CITY_COORDS, SearchConfig
from job_parser.discovery import FilterOption, discover_filter_catalog


WORKPLACE_OPTIONS = ["Remote", "Hybrid", "Onsite"]
COMMITMENT_OPTIONS = ["Full Time", "Part Time", "Contract"]
SENIORITY_OPTIONS = ["Entry", "Junior", "Associate", "Intern", "Graduate", "Unspecified"]
REMOTE_SCOPE_OPTIONS = ["Europe", "Worldwide"]
OUTPUT_OPTIONS = ["Markdown", "JSON"]
LOCATION_MODES = [
    "No city filter",
    "Select available locations",
    "Enter custom city names",
    "Use radius filter",
]


def collect_config(defaults: SearchConfig | None = None) -> SearchConfig:
    base = defaults or SearchConfig()
    questionary = _load_questionary()
    style = questionary.Style(
        [
            ("qmark", "fg:#7aa2f7 bold"),
            ("question", "fg:#d8e6b5 bold"),
            ("answer", "fg:#9ece6a bold"),
            ("pointer", "fg:#e7d79a bold"),
            ("highlighted", "fg:#e7d79a bold"),
            ("selected", "fg:#e7d79a"),
            ("separator", "fg:#565f89"),
            ("instruction", "fg:#7dcfff"),
            ("text", "fg:#d8e6b5"),
        ]
    )

    catalog = discover_filter_catalog(base.base_url)
    keywords = prompt_keyword_editor(questionary, style, base.keywords)
    keywords = prompt_skill_selector(questionary, style, keywords, catalog.skills)
    workplace_types = prompt_checkbox(
        questionary,
        style,
        "Workplace types",
        WORKPLACE_OPTIONS,
        base.workplace_types,
    )
    allowed_countries = prompt_country_scope(questionary, style, base.allowed_countries, catalog.countries)
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
        catalog.locations,
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
    include_seen = prompt_yes_no(
        questionary,
        style,
        "Include previously seen jobs?",
        default=base.include_seen,
    )

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

    if not prompt_yes_no(
        questionary,
        style,
        f"{render_summary(config)}\n\nStart scraping with these settings?",
        default=True,
    ):
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
        keyword_summary = ", ".join(keywords) if keywords else "No keywords selected"
        choices = []
        if keywords:
            choices.append(
                questionary.Choice(
                    f"Edit selected keywords ({keyword_summary})",
                    value="edit",
                )
            )
        choices.extend(
            [
                questionary.Choice("Add another keyword", value="add"),
                questionary.Choice("Continue", value="continue"),
            ]
        )
        action = questionary.select(
            "Keywords",
            choices=choices,
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
            if not keywords:
                questionary.print("Add at least one keyword before continuing.", style="fg:#f7768e")
                continue
            return keywords


def prompt_skill_selector(questionary, style, keywords: list[str], skills: list[str]) -> list[str]:
    if not skills:
        return keywords

    try:
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import HSplit, Layout
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.containers import Window
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: prompt_toolkit\n"
            "Install it with `python3 -m pip install -r requirements.txt`."
        ) from exc

    selected = list(keywords)
    query = ""
    cursor = 0
    result: list[str] | None = None

    def selected_skill_summary() -> str:
        selected_set = {value.casefold() for value in selected}
        selected_skills = [skill for skill in skills if skill.casefold() in selected_set]
        summary = ", ".join(selected_skills[:6])
        if len(selected_skills) > 6:
            summary += ", ..."
        return summary

    def filtered_skills() -> list[str]:
        lowered = query.casefold().strip()
        matches = list(skills)
        if lowered:
            matches = [skill for skill in skills if lowered in skill.casefold()]

        selected_set = {value.casefold() for value in selected}
        chosen = [skill for skill in matches if skill.casefold() in selected_set]
        remaining = [skill for skill in matches if skill.casefold() not in selected_set]
        return [*chosen, *remaining]

    def current_rows() -> list[tuple[str, str | None]]:
        return [("next", None), *[("skill", skill) for skill in filtered_skills()]]

    def clamp_cursor() -> None:
        nonlocal cursor
        rows = current_rows()
        if not rows:
            cursor = 0
            return
        cursor = max(0, min(cursor, len(rows) - 1))

    def render_prompt():
        summary = selected_skill_summary()
        title = "Skills"
        if summary:
            title = f"Skills ({summary})"

        rows = current_rows()
        if not rows:
            rows = [("next", None)]

        text: list[tuple[str, str]] = [
            ("class:question", title),
            ("", "\n"),
            ("class:instruction", "Type to filter. Use arrows to move. Press enter to toggle. Choose Next to continue."),
            ("", "\n\n"),
            ("class:text", f"Search: {query or 'all skills'}"),
            ("", "\n\n"),
        ]

        selected_set = {value.casefold() for value in selected}
        for index, (row_type, value) in enumerate(rows):
            is_active = index == cursor
            marker_style = "class:pointer" if is_active else "class:text"
            label_style = "class:highlighted" if is_active else "class:text"
            pointer = "» " if is_active else "  "
            if row_type == "next":
                marker = "→"
                label = "Next"
            else:
                marker = "✓" if value and value.casefold() in selected_set else "·"
                label = value or ""
            text.extend(
                [
                    (marker_style, pointer),
                    (marker_style, f"{marker} "),
                    (label_style, label),
                    ("", "\n"),
                ]
            )

        if len(rows) == 1:
            text.extend(
                [
                    ("", "\n"),
                    ("class:text", "No skills match the current search."),
                ]
            )

        return text

    control = FormattedTextControl(render_prompt, focusable=True, show_cursor=False)
    window = Window(content=control, always_hide_cursor=True)
    bindings = KeyBindings()

    @bindings.add("up")
    def _move_up(event) -> None:
        nonlocal cursor
        cursor = max(0, cursor - 1)

    @bindings.add("down")
    def _move_down(event) -> None:
        nonlocal cursor
        cursor = min(len(current_rows()) - 1, cursor + 1)

    @bindings.add("backspace")
    def _backspace(event) -> None:
        nonlocal query, cursor
        if query:
            query = query[:-1]
            cursor = 0

    @bindings.add("c-c")
    @bindings.add("c-d")
    @bindings.add("escape")
    def _abort(event) -> None:
        raise SystemExit(0)

    @bindings.add("enter")
    def _enter(event) -> None:
        nonlocal result
        rows = current_rows()
        row_type, value = rows[cursor]
        if row_type == "next":
            result = list(selected)
            event.app.exit()
            return
        if value is None:
            return
        normalized = value.casefold()
        existing = {item.casefold() for item in selected}
        if normalized in existing:
            selected[:] = [item for item in selected if item.casefold() != normalized]
        else:
            selected.append(value)

    @bindings.add("<any>")
    def _type_char(event) -> None:
        nonlocal query, cursor
        if event.data and event.data.isprintable():
            query += event.data
            cursor = 0

    app = Application(
        layout=Layout(HSplit([window])),
        key_bindings=bindings,
        full_screen=False,
        style=style,
    )
    app.run()
    if result is None:
        raise SystemExit(0)
    return result


def prompt_country_scope(questionary, style, default_countries: list[str], options: list[FilterOption]) -> list[str]:
    if options:
        selected_labels = {
            value.casefold()
            for value in default_countries
        }
        default_labels = [
            option.label
            for option in options
            if option.value.casefold() in selected_labels or option.label.casefold() in selected_labels
        ]
        selected = prompt_checkbox(
            questionary,
            style,
            "Countries",
            [option.label for option in options],
            default_labels,
        )
        values_by_label = {option.label: option.value for option in options}
        return [values_by_label[label] for label in selected]

    countries = questionary.text(
        "Custom country codes or names",
        default=",".join(default_countries),
        style=style,
        validate=lambda value: bool(csv_values(value)) or "Enter at least one country.",
    ).ask()
    if countries is None:
        raise SystemExit(0)
    return csv_values(countries)


def prompt_location_details(
    questionary,
    style,
    base: SearchConfig,
    location_mode: str,
    discovered_locations: list[str],
) -> tuple[list[str], str, int | None]:
    if location_mode == "No city filter":
        return [], "", None
    if location_mode == "Select available locations":
        cities = prompt_checkbox(
            questionary,
            style,
            "Select available locations",
            _merge_location_defaults(discovered_locations, base.cities),
            [city for city in base.cities if city in discovered_locations],
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
    selected = list(default)
    selected_set = {item.casefold() for item in selected}
    current_focus: tuple[str, str | None] = ("toggle", options[0]) if options else ("next", None)

    while True:
        choices = [
            questionary.Choice(
                f"{'✓' if option.casefold() in selected_set else '·'} {option}",
                value=("toggle", option),
            )
            for option in options
        ]
        choices.append(questionary.Separator())
        choices.append(questionary.Choice("Next", value=("next", None)))

        result = questionary.select(
            title,
            choices=choices,
            default=current_focus,
            style=style,
            instruction="Use arrows to move. Press enter to toggle. Choose Next to continue.",
        ).ask()
        if result is None:
            raise SystemExit(0)
        action, option = result
        if action == "toggle" and option is not None:
            current_focus = ("toggle", option)
            normalized = option.casefold()
            if normalized in selected_set:
                selected = [item for item in selected if item.casefold() != normalized]
                selected_set.remove(normalized)
            else:
                selected.append(option)
                selected_set.add(normalized)
            continue
        if action == "next":
            if selected or allow_empty:
                return list(selected)
            current_focus = ("next", None)
            questionary.print("Select at least one option.", style="fg:#f7768e")


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


def prompt_yes_no(questionary, style, title: str, default: bool) -> bool:
    default_label = "Yes" if default else "No"
    result = questionary.select(
        title,
        choices=["Yes", "No"],
        default=default_label,
        style=style,
        instruction="Use arrows to move, enter to continue",
    ).ask()
    if result is None:
        raise SystemExit(0)
    return result == "Yes"


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
        return "Select available locations"
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


def _merge_location_defaults(discovered: list[str], selected: list[str]) -> list[str]:
    values = list(discovered)
    seen = {value.casefold() for value in values}
    for value in selected:
        if value.casefold() not in seen:
            values.append(value)
            seen.add(value.casefold())
    return values
