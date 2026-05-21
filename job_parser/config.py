from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse

SENIOR_SENIORITY_TERMS = {"senior", "lead", "principal", "staff", "manager"}
OTHER_SENIORITY_TERMS = {"entry", "junior", "intern", "graduate", "associate", "mid"}
HIRING_CAFE_SENIOR_SENIORITY_LEVELS = ["Senior Level"]
HIRING_CAFE_ENTRY_SENIORITY_LEVELS = [
    "No Prior Experience Required",
    "Entry Level",
    "Mid Level",
]


@dataclass(slots=True)
class SearchConfig:
    keywords: list[str] = field(
        default_factory=lambda: [".NET", "C#", "ASP.NET", "TypeScript", "React"]
    )
    workplace_types: list[str] = field(
        default_factory=lambda: ["Remote", "Hybrid", "Onsite"]
    )
    allowed_countries: list[str] = field(default_factory=lambda: ["DE"])
    remote_scopes: list[str] = field(default_factory=lambda: ["Europe", "Worldwide"])
    seniority_terms: list[str] = field(
        default_factory=lambda: ["entry", "junior", "associate", "intern", "graduate"]
    )
    include_unspecified_seniority: bool = True
    commitments: list[str] = field(default_factory=lambda: ["Full Time"])
    base_url: str = "https://hiring.cafe"
    markdown_output: str = "jobs.md"
    json_output: str = "jobs.json"
    export_markdown: bool = True
    export_json: bool = True
    seen_ids_file: str = "seen_ids.txt"
    include_seen: bool = False
    max_pages: int | None = 500
    cities: list[str] = field(default_factory=list)
    radius_km: int | None = None
    radius_city: str = ""
    session_state_file: str = ""
    browser_profile_dir: str = ""
    search_url: str = ""
    progress_output: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SearchConfig":
        defaults = cls()
        return cls(
            keywords=_normalize_str_list_or_default(payload, "keywords", defaults.keywords),
            workplace_types=_normalize_str_list_or_default(
                payload,
                "workplace_types",
                defaults.workplace_types,
            ),
            allowed_countries=_normalize_str_list_or_default(
                payload,
                "allowed_countries",
                defaults.allowed_countries,
            ),
            remote_scopes=_normalize_str_list_or_default(
                payload,
                "remote_scopes",
                defaults.remote_scopes,
            ),
            seniority_terms=_normalize_str_list_or_default(
                payload,
                "seniority_terms",
                defaults.seniority_terms,
            ),
            include_unspecified_seniority=bool(
                payload.get("include_unspecified_seniority", defaults.include_unspecified_seniority)
            ),
            commitments=_normalize_str_list_or_default(
                payload,
                "commitments",
                defaults.commitments,
            ),
            base_url=str(payload.get("base_url") or defaults.base_url),
            markdown_output=str(payload.get("markdown_output") or defaults.markdown_output),
            json_output=str(payload.get("json_output") or defaults.json_output),
            export_markdown=bool(payload.get("export_markdown", defaults.export_markdown)),
            export_json=bool(payload.get("export_json", defaults.export_json)),
            seen_ids_file=str(payload.get("seen_ids_file") or defaults.seen_ids_file),
            include_seen=bool(payload.get("include_seen", defaults.include_seen)),
            max_pages=_normalize_optional_int(payload.get("max_pages"), defaults.max_pages, preserve_none=True),
            cities=_normalize_str_list(payload.get("cities")),
            radius_km=_normalize_optional_int(payload.get("radius_km"), None, preserve_none=True),
            radius_city=str(payload.get("radius_city") or ""),
            session_state_file=str(payload.get("session_state_file") or ""),
            browser_profile_dir=str(payload.get("browser_profile_dir") or ""),
            search_url=str(payload.get("search_url") or ""),
            progress_output=str(payload.get("progress_output") or ""),
        )


CITY_COORDS: dict[str, tuple[float, float]] = {
    "Berlin": (52.520, 13.405),
    "Munich": (48.137, 11.576),
    "Hamburg": (53.551, 9.993),
    "Frankfurt": (50.110, 8.682),
    "Cologne": (50.938, 6.960),
    "Stuttgart": (48.775, 9.182),
    "Düsseldorf": (51.227, 6.773),
    "Leipzig": (51.340, 12.375),
    "Dortmund": (51.514, 7.465),
    "Dresden": (51.050, 13.737),
    "Hannover": (52.374, 9.738),
    "Nuremberg": (49.453, 11.077),
    "Bremen": (53.075, 8.807),
}

def build_search_state(config: SearchConfig) -> str:
    if config.search_url.strip():
        parsed = parse_search_url(config.search_url)
        if parsed is not None:
            return parsed
    payload: dict[str, object] = {}
    query = " ".join(config.keywords).strip()
    from job_parser.api import build_locations as api_build_locations

    locations = api_build_locations(config)
    seniority_levels = build_seniority_level_filter(config)
    technology_query = build_technology_keywords_query(config)
    if query:
        payload["searchQuery"] = query
    if technology_query:
        payload["technologyKeywordsQuery"] = technology_query
    if seniority_levels:
        payload["seniorityLevel"] = seniority_levels
    if locations:
        payload["locations"] = locations
    return quote_plus(json.dumps(payload, separators=(",", ":")))


def parse_search_url(value: str) -> str | None:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    query = parse_qs(parsed.query)
    search_state = query.get("searchState")
    if not search_state:
        return None
    return quote_plus(search_state[0])


def is_senior_scope(config: SearchConfig) -> bool:
    selected_terms = {term.casefold() for term in config.seniority_terms}
    return bool(selected_terms & SENIOR_SENIORITY_TERMS)


def build_seniority_level_filter(config: SearchConfig) -> list[str]:
    selected_terms = {term.casefold() for term in config.seniority_terms}
    if not selected_terms:
        return []
    if is_senior_scope(config):
        return list(HIRING_CAFE_SENIOR_SENIORITY_LEVELS)
    if selected_terms & OTHER_SENIORITY_TERMS:
        return list(HIRING_CAFE_ENTRY_SENIORITY_LEVELS)
    return []


def build_technology_keywords_query(config: SearchConfig) -> str:
    keywords = [keyword.strip() for keyword in config.keywords if keyword.strip()]
    if len(keywords) <= 1:
        return ""
    quoted = [f'"{keyword}"' for keyword in keywords]
    return " AND ".join(quoted)


def load_seen_ids(path: str | Path) -> set[str]:
    file_path = Path(path)
    if not file_path.exists():
        return set()
    return {
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def save_seen_ids(path: str | Path, new_ids: list[str]) -> None:
    with Path(path).open("a", encoding="utf-8") as file_obj:
        for object_id in new_ids:
            file_obj.write(object_id + "\n")


def load_search_config(path: str | Path) -> SearchConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Config file must contain a JSON object.")
    return SearchConfig.from_dict(payload)


def save_search_config(path: str | Path, config: SearchConfig) -> None:
    Path(path).write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalize_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _normalize_str_list_or_default(
    payload: dict[str, object],
    key: str,
    default: list[str],
) -> list[str]:
    if key not in payload:
        return list(default)
    return _normalize_str_list(payload.get(key))


def _normalize_optional_int(
    value: object,
    default: int | None,
    preserve_none: bool = False,
) -> int | None:
    if value is None:
        return None if preserve_none else default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return default
