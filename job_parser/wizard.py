from __future__ import annotations

from job_parser.config import CITY_COORDS, DEFAULT_DEPARTMENTS, SearchConfig
from job_parser.discovery import discover_filter_catalog
from job_parser.loading import run_with_loading
from job_parser.presets import PRESETS_DIR, save_preset


WORKPLACE_OPTIONS = ["Remote", "Hybrid", "Onsite"]
COMMITMENT_OPTIONS = ["Full Time", "Part Time", "Contract"]
SENIORITY_OPTIONS = [
    "Entry",
    "Junior",
    "Associate",
    "Mid",
    "Senior",
    "Lead",
    "Principal",
    "Staff",
    "Manager",
    "Intern",
    "Graduate",
    "Unspecified",
]
REMOTE_SCOPE_OPTIONS = ["Europe", "Worldwide"]
OUTPUT_OPTIONS = ["Markdown", "JSON"]
SKILL_PAGE_SIZE = 20
COUNTRY_SCOPE_OPTIONS = ["Germany", "International", "Custom countries"]
LOCATION_MODES = [
    "No city filter",
    "Select Germany cities",
    "Enter custom city names",
    "Use radius filter",
]


def collect_config(defaults: SearchConfig | None = None) -> SearchConfig:
    base = defaults or SearchConfig()
    questionary = _load_questionary()
    style = questionary.Style(
        [
            ("qmark", "fg:#7fbbb3 bold"),
            ("question", "fg:#d3c6aa bold"),
            ("answer", "fg:#a7c080 bold"),
            ("pointer", "fg:#e69875 bold noreverse"),
            ("highlighted", "fg:#e69875 bold noreverse"),
            ("selected", "fg:#dbbc7f noreverse"),
            ("separator", "fg:#859289"),
            ("instruction", "fg:#83c092"),
            ("text", "fg:#d3c6aa"),
        ]
    )

    catalog = run_with_loading("Loading live payload options", lambda: discover_filter_catalog(base.base_url))
    keywords = prompt_search_terms(questionary, style, base.keywords, catalog.skills)
    departments = prompt_department_editor(questionary, style, base.departments)
    workplace_types = prompt_checkbox(
        questionary,
        style,
        "Workplace types",
        WORKPLACE_OPTIONS,
        base.workplace_types,
    )
    allowed_countries = prompt_country_scope(questionary, style, base.allowed_countries)
    location_mode_options = _location_mode_options(allowed_countries)
    location_mode = prompt_select(
        questionary,
        style,
        "Location filter",
        location_mode_options,
        _default_location_mode(base, location_mode_options),
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
    include_seen = prompt_yes_no(
        questionary,
        style,
        "Include previously seen jobs?",
        default=base.include_seen,
    )

    config = SearchConfig(
        keywords=keywords,
        departments=departments,
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

    while True:
        action = prompt_start_action(
            questionary,
            style,
            f"{render_summary(config)}\n\nStart scraping with these settings?",
        )
        if action == "start":
            maybe_save_preset(questionary, style, config)
            return config
        if action == "edit":
            return collect_config(config)
        raise SystemExit(0)


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
        f"Departments: {', '.join(config.departments)}",
        f"Workplace types: {', '.join(config.workplace_types)}",
        f"Countries: {render_country_scope(config.allowed_countries)}",
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


def prompt_search_terms(questionary, style, default_keywords: list[str], skills: list[str]) -> list[str]:
    keywords = list(default_keywords)
    while True:
        keyword_summary = ", ".join(keywords[:6]) if keywords else "No terms selected"
        if len(keywords) > 6:
            keyword_summary += ", ..."
        choices = []
        if keywords:
            choices.append(
                questionary.Choice(
                    f"Edit selected terms ({keyword_summary})",
                    value="edit",
                )
            )
        if skills:
            choices.append(
                questionary.Choice("Browse and select skills", value="skills")
            )
        choices.extend(
            [
                questionary.Choice("Add a manual keyword", value="add"),
                questionary.Choice("Continue", value="continue"),
            ]
        )
        action = questionary.select(
            "Search Terms",
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
                questionary.print("Keep at least one term selected.", style="fg:#e67e80")
        elif action == "skills":
            keywords = prompt_skill_selector(questionary, style, keywords, skills)
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
                questionary.print(
                    "Add at least one skill or manual keyword before continuing.",
                    style="fg:#e67e80",
                )
                continue
            return keywords


def prompt_department_editor(questionary, style, default_departments: list[str]) -> list[str]:
    departments = list(default_departments or DEFAULT_DEPARTMENTS)
    while True:
        summary = ", ".join(departments[:4]) if departments else "No departments selected"
        if len(departments) > 4:
            summary += ", ..."
        action = questionary.select(
            "Departments",
            choices=[
                questionary.Choice(f"Edit selected departments ({summary})", value="edit"),
                questionary.Choice("Add a manual department", value="add"),
                questionary.Choice("Continue", value="continue"),
            ],
            style=style,
            instruction="Use arrows to move, enter to continue",
        ).ask()
        if action is None:
            raise SystemExit(0)
        if action == "edit":
            selected = prompt_checkbox(
                questionary,
                style,
                "Toggle the departments you want to keep",
                departments,
                departments,
            )
            if selected:
                departments = selected
            else:
                questionary.print("Keep at least one department selected.", style="fg:#e67e80")
            continue
        if action == "add":
            new_department = questionary.text(
                "New department",
                style=style,
                validate=lambda value: bool(value.strip()) or "Enter a department.",
            ).ask()
            if new_department is None:
                raise SystemExit(0)
            normalized = {department.casefold() for department in departments}
            if new_department.strip().casefold() not in normalized:
                departments.append(new_department.strip())
            continue
        if departments:
            return departments
        questionary.print("Keep at least one department selected.", style="fg:#e67e80")


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
        return [("back", None), ("next", None), *[("skill", skill) for skill in filtered_skills()]]

    def total_pages() -> int:
        skill_count = max(0, len(current_rows()) - 2)
        return max(1, (skill_count + SKILL_PAGE_SIZE - 1) // SKILL_PAGE_SIZE)

    def page_start_index(page_number: int) -> int:
        if page_number <= 1:
            return 2
        return 2 + (page_number - 1) * SKILL_PAGE_SIZE

    def current_page() -> int:
        if cursor <= 1:
            return 1
        return min(((cursor - 2) // SKILL_PAGE_SIZE) + 1, total_pages())

    def visible_rows() -> tuple[list[tuple[str, str | None]], int, int]:
        rows = current_rows()
        if len(rows) <= 2:
            return rows, 1, 1

        page_count = total_pages()
        page_index = current_page() - 1
        start = 2 + page_index * SKILL_PAGE_SIZE
        end = min(start + SKILL_PAGE_SIZE, len(rows))
        return [rows[0], rows[1], *rows[start:end]], page_index + 1, page_count

    def render_prompt():
        summary = selected_skill_summary()
        title = "Skills"
        if summary:
            title = f"Skills ({summary})"

        all_rows = current_rows()
        rows, current_page, total_pages = visible_rows()
        if not rows:
            rows = [("next", None)]

        text: list[tuple[str, str]] = [
            ("class:question", title),
            ("", "\n"),
            ("class:instruction", "Type to filter. Up/down move within a page. Left/right change pages. Enter toggles. Back returns to search terms."),
            ("", "\n\n"),
            ("class:text", f"Search: {query or 'all skills'}"),
            ("", "\n\n"),
        ]

        if len(all_rows) > 1:
            text.extend(
                [
                    ("class:text", f"Page {current_page}/{total_pages}"),
                    ("", "\n\n"),
                ]
            )

        selected_set = {value.casefold() for value in selected}
        for row_type, value in rows:
            is_active = (row_type, value) == current_rows()[cursor]
            marker_style = "class:pointer" if is_active else "class:text"
            label_style = "class:highlighted" if is_active else "class:text"
            pointer = "» " if is_active else "  "
            if row_type == "back":
                marker = "←"
                label = "Back"
            elif row_type == "next":
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
        if cursor <= 2:
            cursor = max(0, cursor - 1)
            return
        page = current_page()
        start = page_start_index(page)
        if cursor > start:
            cursor -= 1

    @bindings.add("down")
    def _move_down(event) -> None:
        nonlocal cursor
        rows = current_rows()
        if cursor == 0:
            cursor = min(1, len(rows) - 1)
            return
        if cursor == 1:
            cursor = min(2, len(rows) - 1)
            return
        page = current_page()
        start = page_start_index(page)
        end = min(start + SKILL_PAGE_SIZE - 1, len(rows) - 1)
        if cursor < end:
            cursor += 1

    @bindings.add("left")
    def _page_left(event) -> None:
        nonlocal cursor
        if cursor <= 1:
            return
        page = current_page()
        if page <= 1:
            return
        offset = cursor - page_start_index(page)
        target_page = page - 1
        target_start = page_start_index(target_page)
        target_end = min(target_start + SKILL_PAGE_SIZE - 1, len(current_rows()) - 1)
        cursor = min(target_start + offset, target_end)

    @bindings.add("right")
    def _page_right(event) -> None:
        nonlocal cursor
        if cursor <= 1:
            return
        page = current_page()
        page_count = total_pages()
        if page >= page_count:
            return
        offset = cursor - page_start_index(page)
        target_page = page + 1
        target_start = page_start_index(target_page)
        target_end = min(target_start + SKILL_PAGE_SIZE - 1, len(current_rows()) - 1)
        cursor = min(target_start + offset, target_end)

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
        if row_type == "back":
            result = list(selected)
            event.app.exit()
            return
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


def prompt_country_scope(questionary, style, default_countries: list[str]) -> list[str]:
    default_scope = _default_country_scope(default_countries)
    scope = prompt_select(
        questionary,
        style,
        "Country scope",
        COUNTRY_SCOPE_OPTIONS,
        default_scope,
    )
    if scope == "Germany":
        return ["DE"]
    if scope == "Custom countries":
        countries = questionary.text(
            "Custom country codes or names",
            default=",".join(default_countries),
            style=style,
            validate=lambda value: bool(csv_values(value)) or "Enter at least one country.",
        ).ask()
        if countries is None:
            raise SystemExit(0)
        return csv_values(countries)
    return []


def prompt_location_details(
    questionary,
    style,
    base: SearchConfig,
    location_mode: str,
) -> tuple[list[str], str, int | None]:
    if location_mode == "No city filter":
        return [], "", None
    if location_mode == "Select Germany cities":
        cities = prompt_checkbox(
            questionary,
            style,
            "Select Germany cities",
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
            questionary.print("Select at least one option.", style="fg:#e67e80")


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


def prompt_start_action(questionary, style, title: str) -> str:
    result = questionary.select(
        title,
        choices=[
            questionary.Choice("Start scraping", value="start"),
            questionary.Choice("Edit settings", value="edit"),
            questionary.Choice("Cancel", value="cancel"),
        ],
        default="start",
        style=style,
        instruction="Use arrows to move, enter to continue",
    ).ask()
    if result is None:
        raise SystemExit(0)
    return str(result)


def maybe_save_preset(questionary, style, config: SearchConfig) -> None:
    if not prompt_yes_no(
        questionary,
        style,
        f"Save this search as a preset in `{PRESETS_DIR}/`?",
        default=False,
    ):
        return

    preset_name = questionary.text(
        "Preset name",
        style=style,
        validate=lambda value: bool(value.strip()) or "Enter a preset name.",
    ).ask()
    if preset_name is None:
        raise SystemExit(0)

    preset_description = questionary.text(
        "Preset description (optional)",
        style=style,
        default="",
    ).ask()
    if preset_description is None:
        raise SystemExit(0)

    preset = save_preset(
        name=preset_name.strip(),
        description=preset_description.strip(),
        config=config,
    )
    questionary.print(
        f"Saved preset → {preset.path}",
        style="fg:#a7c080",
    )


def csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def render_country_scope(allowed_countries: list[str]) -> str:
    if not allowed_countries:
        return "International"
    if len(allowed_countries) == 1 and _includes_germany(allowed_countries):
        return "Germany"
    return ", ".join(allowed_countries)


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


def _default_location_mode(config: SearchConfig, allowed_modes: list[str]) -> str:
    if config.radius_km and config.radius_city:
        preferred = "Use radius filter"
        return preferred if preferred in allowed_modes else allowed_modes[0]
    if config.cities:
        preferred = "Select Germany cities" if any(city in CITY_COORDS for city in config.cities) else "Enter custom city names"
        return preferred if preferred in allowed_modes else allowed_modes[0]
    return "No city filter" if "No city filter" in allowed_modes else allowed_modes[0]


def _load_questionary():
    try:
        import questionary
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: questionary\n"
            "Install it with `python3 -m pip install -r requirements.txt`."
        ) from exc
    return questionary


def _location_mode_options(allowed_countries: list[str]) -> list[str]:
    if _includes_germany(allowed_countries):
        return list(LOCATION_MODES)
    return [
        "No city filter",
        "Enter custom city names",
    ]


def _includes_germany(allowed_countries: list[str]) -> bool:
    normalized = {value.casefold() for value in allowed_countries}
    return "de" in normalized or "germany" in normalized


def _default_country_scope(allowed_countries: list[str]) -> str:
    if not allowed_countries:
        return "International"
    if len(allowed_countries) == 1 and _includes_germany(allowed_countries):
        return "Germany"
    return "Custom countries"
