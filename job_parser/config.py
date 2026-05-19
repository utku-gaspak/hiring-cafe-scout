from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote


@dataclass(slots=True)
class SearchConfig:
    keywords: list[str] = field(
        default_factory=lambda: [".NET", "C#", "ASP.NET", "TypeScript", "React"]
    )
    base_url: str = "https://hiring.cafe"
    markdown_output: str = "jobs.md"
    json_output: str = "jobs.json"
    seen_ids_file: str = "seen_ids.txt"
    max_pages: int | None = 500
    cities: list[str] = field(default_factory=list)
    radius_km: int | None = None
    radius_city: str = ""


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

SERVER_FILTER_SEARCH_STATE = quote(
    json.dumps(
        {
            "seniorityLevel": ["Entry Level"],
            "commitmentTypes": ["Full Time"],
            "departments": [
                "Software Development",
                "Information Technology",
                "Engineering",
            ],
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
