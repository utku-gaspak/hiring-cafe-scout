from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from contextlib import suppress
import json
import re
import sys
from urllib.error import HTTPError, URLError
from html import unescape
from urllib.request import Request, urlopen

from job_parser.config import DEFAULT_DEPARTMENTS


NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
OPTION_KEYS = ("label", "name", "title", "value")
VALUE_KEYS = ("value", "code", "id", "key")
SKILL_TERMS = {
    "react",
    "next.js",
    "nest.js",
    "express.js",
    "graphql",
    "rest",
    "jwt",
    "oauth2",
    "kafka",
    "websockets",
    "typescript",
    "redux",
    "zustand",
    "tailwindcss",
    "styled components",
    "postgresql",
    "prisma",
    "google cloud platform",
    "cloud run",
    "functions",
    "github actions",
    "docker",
    "kubernetes",
}
COUNTRY_LABELS = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "CH": "Switzerland",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HR": "Croatia",
    "HU": "Hungary",
    "IE": "Ireland",
    "IT": "Italy",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "MT": "Malta",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
}


@dataclass(frozen=True, slots=True)
class FilterOption:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class FilterCatalog:
    departments: list[str]
    countries: list[FilterOption]
    locations: list[str]
    skills: list[str]


def discover_departments(base_url: str) -> list[str]:
    return discover_filter_catalog(base_url).departments


def discover_filter_catalog(base_url: str) -> FilterCatalog:
    try:
        payload = fetch_next_data_payload(base_url)
        departments = extract_departments_from_payload(payload) or list(DEFAULT_DEPARTMENTS)
        countries = extract_countries_from_payload(payload)
        locations = extract_locations_from_payload(payload)
        skills = extract_skills_from_payload(payload)
        return FilterCatalog(
            departments=departments,
            countries=countries,
            locations=locations,
            skills=skills,
        )
    except Exception as exc:
        print(
            f"Warning: could not inspect hiring.cafe payload ({exc}); "
            "falling back to built-in defaults.",
            file=sys.stderr,
        )
        return FilterCatalog(
            departments=list(DEFAULT_DEPARTMENTS),
            countries=[],
            locations=[],
            skills=[],
        )


def build_payload_inspection_report(payload: dict) -> str:
    page_props = payload.get("props", {}).get("pageProps", {})
    lines: list[str] = []

    if isinstance(page_props, dict):
        lines.append("pageProps keys:")
        lines.append("  " + ", ".join(sorted(str(key) for key in page_props.keys())))
        filters = page_props.get("filters")
        if isinstance(filters, dict):
            lines.append("filters keys:")
            lines.append("  " + ", ".join(sorted(str(key) for key in filters.keys())))
    else:
        lines.append("pageProps: <missing or non-dict>")

    lines.append("")
    lines.append("candidate catalog matches:")
    lines.extend(_format_candidate_matches(payload))
    return "\n".join(lines)


def fetch_next_data_payload(base_url: str) -> dict:
    html = _fetch_html_via_http(base_url)
    if html is None:
        html = _fetch_html_via_playwright(base_url)
    if html is None:
        raise ValueError("Could not fetch homepage HTML.")

    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise ValueError("Could not locate __NEXT_DATA__ payload in homepage HTML.")
    return json.loads(unescape(match.group(1)))


def _fetch_html_via_http(base_url: str) -> str | None:
    request = Request(
        base_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError):
        return None


def _fetch_html_via_playwright(base_url: str) -> str | None:
    with suppress(ModuleNotFoundError):
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as playwright_timeout

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                try:
                    page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
                except playwright_timeout:
                    page.goto(base_url, wait_until="commit", timeout=30_000)
                page.wait_for_timeout(2_000)
                return page.content()
            finally:
                browser.close()
    return None


def extract_departments_from_payload(payload: dict) -> list[str]:
    departments = _extract_best_string_candidate(
        payload,
        keyword="department",
        preferred_values=DEFAULT_DEPARTMENTS,
        extra_keywords=("categories", "category", "dept", "departments", "sectors"),
    )
    if _looks_like_skill_list(departments):
        return []
    return departments


def extract_countries_from_payload(payload: dict) -> list[FilterOption]:
    options = _extract_best_option_candidate(
        payload,
        keyword="country",
        preferred_values=[],
        extra_keywords=("countries",),
    )
    return [_normalize_country_option(option) for option in options]


def extract_locations_from_payload(payload: dict) -> list[str]:
    return _extract_best_string_candidate(
        payload,
        keyword="location",
        preferred_values=[],
        extra_keywords=("region", "regions", "locations"),
    )


def extract_skills_from_payload(payload: dict) -> list[str]:
    aggregated = _extract_skills_from_hits(payload)
    if aggregated:
        return aggregated
    candidates = _collect_skill_candidates(payload)
    if not candidates:
        return []
    best = candidates[0][2]
    return _dedupe_preserve_order([option.label for option in best])


def _normalize_option_list(values: list[object]) -> list[FilterOption]:
    return _normalize_option_list_with_minimum(values, min_items=1)


def _normalize_option_list_with_minimum(
    values: list[object],
    min_items: int,
) -> list[FilterOption]:
    if not values:
        return []
    if all(isinstance(value, str) for value in values):
        normalized = [
            FilterOption(label=str(value).strip(), value=str(value).strip())
            for value in values
            if _is_readable_label(str(value).strip())
        ]
        return normalized if len(normalized) >= min_items else []
    if all(isinstance(value, dict) for value in values):
        extracted: list[FilterOption] = []
        for value in values:
            text = None
            for key in OPTION_KEYS:
                raw = value.get(key)
                if isinstance(raw, str) and _is_readable_label(raw.strip()):
                    text = raw.strip()
                    break
            if text:
                raw_value = ""
                for key in VALUE_KEYS:
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        raw_value = candidate.strip()
                        break
                extracted.append(FilterOption(label=text, value=raw_value or text))
        return extracted if len(extracted) >= min_items else []
    return []


def _is_readable_label(value: str) -> bool:
    if not value:
        return False
    if len(value) < 2:
        return False
    if " " in value:
        return True
    if any(char in value for char in ("&", "/", "-", ".", "(", ")")):
        return True
    if not value.isalnum():
        return True
    has_lower = any(char.islower() for char in value)
    has_upper = any(char.isupper() for char in value)
    has_digit = any(char.isdigit() for char in value)
    if has_upper and has_lower and has_digit and len(value) >= 12:
        return False
    if has_digit and len(value) >= 10:
        return False
    return any(char.isalpha() for char in value)


def _looks_like_skill_list(values: list[str]) -> bool:
    if len(values) < 3:
        return False
    hits = 0
    for value in values:
        normalized = value.casefold()
        if normalized in SKILL_TERMS:
            hits += 1
            continue
        if any(token in normalized for token in (".js", "css", "graphql", "oauth", "jwt")):
            hits += 1
            continue
        if any(
            token in normalized
            for token in (
                "docker",
                "kubernetes",
                "postgres",
                "prisma",
                "tailwind",
                "redux",
                "zustand",
                "react",
                "typescript",
                "github actions",
                "cloud",
                "kafka",
                "websocket",
            )
        ):
            hits += 1
    return hits >= max(3, len(values) // 3)


def _score_skill_candidate(path: tuple[str, ...], values: list[str]) -> int:
    lowered_path = " ".join(path).lower()
    score = 0
    if any(
        keyword in lowered_path
        for keyword in (
            "skill",
            "skills",
            "tool",
            "tools",
            "technology",
            "technologies",
            "stack",
            "framework",
            "frameworks",
        )
    ):
        score += 120
    if _looks_like_skill_list(values):
        score += 80
    if len(values) >= 5:
        score += min(len(values), 50)
    return score


def _extract_skills_from_hits(payload: dict) -> list[str]:
    hits = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("ssrHits", [])
    )
    if not isinstance(hits, list):
        return []

    counts: Counter[str] = Counter()
    display_by_key: dict[str, str] = {}
    first_seen: dict[str, int] = {}
    order = 0

    for hit in hits:
        if not isinstance(hit, dict):
            continue
        technical_tools = (
            hit.get("v5_processed_job_data", {})
            .get("technical_tools", [])
        )
        if not isinstance(technical_tools, list):
            continue
        seen_in_hit: set[str] = set()
        for raw in technical_tools:
            if not isinstance(raw, str):
                continue
            skill = raw.strip()
            if not _is_readable_label(skill):
                continue
            key = skill.casefold()
            if key in seen_in_hit:
                continue
            seen_in_hit.add(key)
            counts[key] += 1
            display_by_key.setdefault(key, skill)
            first_seen.setdefault(key, order)
            order += 1

    ranked = sorted(
        counts,
        key=lambda key: (-counts[key], first_seen[key], display_by_key[key].casefold()),
    )
    return [display_by_key[key] for key in ranked]


def _score_candidate(
    path: tuple[str, ...],
    values: list[str],
    keyword: str,
    preferred_values: list[str],
    extra_keywords: tuple[str, ...] = (),
) -> int:
    lowered_path = " ".join(path).lower()
    score = 0
    if keyword in lowered_path:
        score += 100
    if any(extra in lowered_path for extra in extra_keywords):
        score += 60
    overlap = sum(1 for preferred in preferred_values if preferred in values)
    score += overlap * 20
    if overlap >= 2:
        score += 40
    if len(values) >= 5:
        score += min(len(values), 50)
    return score


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_best_string_candidate(
    payload: dict,
    keyword: str,
    preferred_values: list[str],
    extra_keywords: tuple[str, ...] = (),
) -> list[str]:
    candidates = _collect_candidates(payload, keyword, preferred_values, extra_keywords)
    if not candidates:
        return []
    best = candidates[0][2]
    return _dedupe_preserve_order([option.label for option in best])


def _extract_best_option_candidate(
    payload: dict,
    keyword: str,
    preferred_values: list[str],
    extra_keywords: tuple[str, ...] = (),
) -> list[FilterOption]:
    candidates = _collect_candidates(payload, keyword, preferred_values, extra_keywords)
    if not candidates:
        return []
    best = candidates[0][2]
    deduped: list[FilterOption] = []
    seen: set[str] = set()
    for option in best:
        key = option.value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(option)
    return deduped


def _collect_candidates(
    payload: dict,
    keyword: str,
    preferred_values: list[str],
    extra_keywords: tuple[str, ...] = (),
) -> list[tuple[int, tuple[str, ...], list[FilterOption]]]:
    candidates: list[tuple[int, tuple[str, ...], list[FilterOption]]] = []

    def visit(node: object, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                visit(value, path + (str(key),))
            return
        if isinstance(node, list):
            option_values = _normalize_option_list_with_minimum(node, min_items=1)
            if option_values:
                labels = [option.label for option in option_values]
                score = _score_candidate(path, labels, keyword, preferred_values, extra_keywords)
                if score > 0:
                    candidates.append((score, path, option_values))
            for item in node:
                visit(item, path)

    visit(payload, tuple())
    candidates.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    return candidates


def _collect_skill_candidates(payload: dict) -> list[tuple[int, tuple[str, ...], list[FilterOption]]]:
    candidates: list[tuple[int, tuple[str, ...], list[FilterOption]]] = []

    def visit(node: object, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                visit(value, path + (str(key),))
            return
        if isinstance(node, list):
            option_values = _normalize_option_list_with_minimum(node, min_items=1)
            if option_values:
                labels = [option.label for option in option_values]
                score = _score_skill_candidate(path, labels)
                if score > 0:
                    candidates.append((score, path, option_values))
            for item in node:
                visit(item, path)

    visit(payload, tuple())
    candidates.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    return candidates


def _format_candidate_matches(payload: dict, limit: int = 5) -> list[str]:
    sections = [
        (
            "departments",
            _collect_candidates(
                payload,
                keyword="department",
                preferred_values=DEFAULT_DEPARTMENTS,
                extra_keywords=("categories", "category", "dept", "departments", "sectors"),
            ),
        ),
        (
            "countries",
            _collect_candidates(
                payload,
                keyword="country",
                preferred_values=[],
                extra_keywords=("countries",),
            ),
        ),
        (
            "locations",
            _collect_candidates(
                payload,
                keyword="location",
                preferred_values=[],
                extra_keywords=("region", "regions", "locations"),
            ),
        ),
        ("skills", _collect_skill_candidates(payload)),
    ]

    lines: list[str] = []
    for section_name, candidates in sections:
        lines.append(f"{section_name}:")
        if not candidates:
            lines.append("  (none)")
            continue
        for score, path, options in candidates[:limit]:
            labels = ", ".join(option.label for option in options[:10])
            lines.append(f"  score={score} path={'/'.join(path) or '<root>'}")
            lines.append(f"    {labels}")
    return lines


def _normalize_country_option(option: FilterOption) -> FilterOption:
    value = option.value.strip().upper()
    label = option.label.strip()
    if value in COUNTRY_LABELS:
        return FilterOption(label=COUNTRY_LABELS[value], value=value)
    upper_label = label.upper()
    if upper_label in COUNTRY_LABELS:
        return FilterOption(label=COUNTRY_LABELS[upper_label], value=upper_label)
    return option
