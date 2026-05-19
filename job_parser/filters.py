from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt

from job_parser.config import CITY_COORDS, SearchConfig
from job_parser.models import Job


SENIOR_LEVELS = {"senior level", "mid level", "lead", "principal", "staff", "manager"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * radius_km * atan2(sqrt(a), sqrt(1 - a))


def matches_keyword(job: Job, config: SearchConfig) -> bool:
    title = job.title.lower()
    tools = " ".join(job.technical_tools).lower()
    summary = job.requirements_summary.lower()
    haystack = f"{title} {tools} {summary}"
    return any(keyword.lower() in haystack for keyword in config.keywords)


def matches_seniority(job: Job) -> bool:
    seniority = job.seniority_level.lower().strip()
    if not seniority:
        return True
    if any(level in seniority for level in ("entry", "junior", "associate", "intern", "graduate")):
        return True
    return not any(level in seniority for level in SENIOR_LEVELS)


def matches_commitment(job: Job) -> bool:
    values = job.commitments or ([job.commitment] if job.commitment else [])
    return any("full" in value.lower() for value in values)


def matches_location(job: Job, config: SearchConfig) -> bool:
    work_type = job.work_type.lower()

    if "remote" in work_type:
        if "Europe" in job.continents or job.worldwide_remote:
            return True

    if "DE" not in job.countries:
        return False

    if not config.cities and not (config.radius_km and config.radius_city):
        return True

    if (
        config.radius_km
        and config.radius_city
        and config.radius_city in CITY_COORDS
    ):
        target_lat, target_lon = CITY_COORDS[config.radius_city]
        for geo in job.geolocations:
            if haversine_km(target_lat, target_lon, geo.lat, geo.lon) <= config.radius_km:
                return True
        return False

    return any(
        city_filter.lower() in city.lower()
        for city in job.cities
        for city_filter in config.cities
    )

