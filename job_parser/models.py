from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(slots=True)
class Job:
    object_id: str
    source: str
    title: str
    raw_title: str
    company: str
    location: str
    work_type: str
    commitment: str
    commitments: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    continents: list[str] = field(default_factory=list)
    worldwide_remote: bool = False
    technical_tools: list[str] = field(default_factory=list)
    requirements_summary: str = ""
    seniority_level: str = ""
    min_years_experience: int | None = None
    posted_str: str = "Unknown"
    date_obj: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=timezone.utc)
    )
    url: str = ""
    apply_url: str = ""
    geolocations: list[GeoPoint] = field(default_factory=list)

