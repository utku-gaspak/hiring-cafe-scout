from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class GeoPoint:
    lat: float
    lon: float

    def to_dict(self) -> dict[str, float]:
        return {"lat": self.lat, "lon": self.lon}


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

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.object_id,
            "source": self.source,
            "title": self.title,
            "raw_title": self.raw_title,
            "company": self.company,
            "location_display": self.location,
            "workplace_type": self.work_type,
            "commitment": self.commitment,
            "commitments": self.commitments,
            "cities": self.cities,
            "countries": self.countries,
            "continents": self.continents,
            "worldwide_remote": self.worldwide_remote,
            "technical_tools": self.technical_tools,
            "requirements_summary": self.requirements_summary,
            "seniority_level": self.seniority_level,
            "min_years_experience": self.min_years_experience,
            "posted_at": self.posted_str,
            "job_url": self.url,
            "apply_url": self.apply_url,
            "geolocations": [geo.to_dict() for geo in self.geolocations],
        }


def sort_jobs(jobs: list[Job]) -> list[Job]:
    return sorted(jobs, key=lambda job: job.date_obj, reverse=True)
