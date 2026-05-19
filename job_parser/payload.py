from __future__ import annotations

import re
from datetime import datetime, timezone

from job_parser.models import GeoPoint, Job


def parse_job(hit: dict, url: str) -> Job:
    processed = hit.get("v5_processed_job_data") or {}
    job_information = hit.get("job_information") or {}
    company_data = hit.get("enriched_company_data") or {}

    raw_title = job_information.get("title") or ""
    title = (
        processed.get("core_job_title")
        or re.sub(r"\s*\([^)]*\)", "", raw_title).strip()
        or "Unknown"
    )
    company = company_data.get("name") or processed.get("company_name") or "Unknown"
    location = processed.get("formatted_workplace_location") or "Unknown"
    commitment_raw = processed.get("commitment") or []
    commitments = _normalize_str_list(commitment_raw)
    commitment = commitments[0] if commitments else str(commitment_raw or "")

    timestamp_ms = processed.get("estimated_publish_date_millis")
    if timestamp_ms:
        date_obj = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        posted_str = date_obj.strftime("%Y-%m-%d")
    else:
        date_obj = datetime.min.replace(tzinfo=timezone.utc)
        posted_str = processed.get("estimated_publish_date") or "Unknown"

    continents = _normalize_str_list(processed.get("workplace_continents"))
    continents.extend(_normalize_str_list(processed.get("boundless_workplace_continents")))

    geolocations = []
    for geo in hit.get("_geoloc") or []:
        lat = geo.get("lat")
        lon = geo.get("lon")
        if lat is None or lon is None:
            continue
        geolocations.append(GeoPoint(lat=lat, lon=lon))

    min_years_experience = processed.get("min_industry_and_role_yoe")
    if not isinstance(min_years_experience, int):
        min_years_experience = None

    return Job(
        object_id=hit.get("objectID") or hit.get("id") or "",
        source=str(hit.get("source") or ""),
        title=title,
        raw_title=raw_title,
        company=company,
        location=location,
        work_type=str(processed.get("workplace_type") or ""),
        commitment=commitment,
        commitments=commitments,
        cities=_normalize_str_list(processed.get("workplace_cities")),
        countries=_normalize_str_list(processed.get("workplace_countries")),
        continents=continents,
        worldwide_remote=bool(processed.get("is_workplace_worldwide_ok")),
        technical_tools=_normalize_str_list(processed.get("technical_tools")),
        requirements_summary=str(processed.get("requirements_summary") or ""),
        seniority_level=str(processed.get("seniority_level") or ""),
        min_years_experience=min_years_experience,
        posted_str=posted_str,
        date_obj=date_obj,
        url=url,
        apply_url=str(hit.get("apply_url") or ""),
        geolocations=geolocations,
    )


def _normalize_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []

