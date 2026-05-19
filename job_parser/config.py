from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

DEFAULT_DEPARTMENTS = [
    "Software Development",
    "Information Technology",
    "Engineering",
]


@dataclass(slots=True)
class SearchConfig:
    keywords: list[str] = field(
        default_factory=lambda: [".NET", "C#", "ASP.NET", "TypeScript", "React"]
    )
    departments: list[str] = field(default_factory=lambda: list(DEFAULT_DEPARTMENTS))
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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SearchConfig":
        return cls(
            keywords=_normalize_str_list(payload.get("keywords"))
            or cls().keywords,
            departments=_normalize_str_list(payload.get("departments"))
            or cls().departments,
            workplace_types=_normalize_str_list(payload.get("workplace_types"))
            or cls().workplace_types,
            allowed_countries=_normalize_str_list(payload.get("allowed_countries"))
            or cls().allowed_countries,
            remote_scopes=_normalize_str_list(payload.get("remote_scopes"))
            or cls().remote_scopes,
            seniority_terms=_normalize_str_list(payload.get("seniority_terms"))
            or cls().seniority_terms,
            include_unspecified_seniority=bool(
                payload.get("include_unspecified_seniority", cls().include_unspecified_seniority)
            ),
            commitments=_normalize_str_list(payload.get("commitments"))
            or cls().commitments,
            base_url=str(payload.get("base_url") or cls().base_url),
            markdown_output=str(payload.get("markdown_output") or cls().markdown_output),
            json_output=str(payload.get("json_output") or cls().json_output),
            export_markdown=bool(payload.get("export_markdown", cls().export_markdown)),
            export_json=bool(payload.get("export_json", cls().export_json)),
            seen_ids_file=str(payload.get("seen_ids_file") or cls().seen_ids_file),
            include_seen=bool(payload.get("include_seen", cls().include_seen)),
            max_pages=_normalize_optional_int(payload.get("max_pages"), cls().max_pages, preserve_none=True),
            cities=_normalize_str_list(payload.get("cities")),
            radius_km=_normalize_optional_int(payload.get("radius_km"), None, preserve_none=True),
            radius_city=str(payload.get("radius_city") or ""),
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
    return quote(
        json.dumps(
            {
                "seniorityLevel": ["Entry Level"],
                "commitmentTypes": ["Full Time"],
                "departments": config.departments,
            }
        )
    )


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
