from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from job_parser.config import (
    CITY_COORDS,
    SearchConfig,
    build_seniority_level_filter,
    build_technology_keywords_query,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from curl_cffi.requests import Session


class CloudflareChallenge(Exception):
    """Raised when a Cloudflare challenge page is detected instead of a real API response."""


class _FallbackSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self._cf_cookies: dict[str, str] = {}

    def post(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - runtime guard
        raise SystemExit(
            "Missing dependency: curl-cffi\n"
            "Install it with `uv sync` and rerun cafe-scout."
        )

    def close(self) -> None:  # pragma: no cover - compatibility no-op
        return None


PAGE_SIZE = 1000
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


def build_search_state(config: SearchConfig) -> dict[str, Any]:
    search_state: dict[str, Any] = {}
    query = " ".join(config.keywords).strip()
    locations = build_locations(config)
    seniority_levels = build_seniority_level_filter(config)
    technology_query = build_technology_keywords_query(config)
    if query:
        search_state["searchQuery"] = query
    if technology_query:
        search_state["technologyKeywordsQuery"] = technology_query
    if seniority_levels:
        search_state["seniorityLevel"] = seniority_levels
    if locations:
        search_state["locations"] = locations
    return search_state


def fetch_total_count(
    config: SearchConfig,
    search_state: dict[str, Any],
    session: Session | None = None,
) -> int | None:
    response = _post_json(
        config,
        f"{config.base_url.rstrip('/')}/api/search-jobs/get-total-count",
        {"searchState": search_state},
        session=session,
    )
    if isinstance(response, dict):
        total = response.get("total")
        if isinstance(total, int):
            return total
        if isinstance(total, str) and total.isdigit():
            return int(total)
    return None


def fetch_jobs_page(
    config: SearchConfig,
    search_state: dict[str, Any],
    page: int,
    size: int = PAGE_SIZE,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    response = _post_json(
        config,
        f"{config.base_url.rstrip('/')}/api/search-jobs",
        {
            "size": size,
            "page": page,
            "searchState": search_state,
        },
        session=session,
    )
    return extract_job_records(response)


def extract_job_records(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if not isinstance(response, dict):
        return []

    for key in ("results", "jobs", "data", "items", "content"):
        value = response.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    hits = response.get("hits")
    if isinstance(hits, dict):
        nested = hits.get("hits")
        if isinstance(nested, list):
            return [
                item.get("_source", item)
                for item in nested
                if isinstance(item, dict)
            ]
    if isinstance(hits, list):
        return [
            item.get("_source", item)
            for item in hits
            if isinstance(item, dict)
        ]

    return []


def build_session(config: SearchConfig) -> Session:
    try:
        from curl_cffi.requests import Session as CurlSession
    except ModuleNotFoundError:  # pragma: no cover - import guard
        session = _FallbackSession()
    else:
        session = CurlSession(impersonate="chrome136")
    session._cf_cookies: dict[str, str] = {}  # type: ignore[attr-defined]
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Referer": f"{config.base_url.rstrip('/')}/",
            "Origin": config.base_url.rstrip("/"),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
    )
    if config.session_state_file:
        load_session_state(session, config.session_state_file)
    return session


def _post_json(
    config: SearchConfig,
    url: str,
    payload: dict[str, Any],
    session: Session | None = None,
) -> Any:
    session = session or build_session(config)
    cf_cookies = getattr(session, "_cf_cookies", {})
    try:
        response = session.post(url, json=payload, timeout=30, cookies=cf_cookies or None)
    except Exception as exc:
        raise SystemExit(f"HiringCafe API request failed: {exc}.") from exc

    if response.status_code >= 400:
        body = response.text.lower()
        cf_server = "cloudflare" in response.headers.get("server", "").lower()
        challenge_detected = (
            response.headers.get("cf-mitigated", "").lower() == "challenge"
            or (cf_server and response.status_code in (403, 503))
            or "just a moment" in body
            or "enable javascript and cookies" in body
            or "security verification" in body
        )
        if challenge_detected:
            raise CloudflareChallenge()
        raise SystemExit(
            f"HiringCafe API request failed with HTTP {response.status_code}. "
            "The site may be blocking automated requests."
        )

    try:
        return response.json()
    except ValueError as exc:
        body = response.text.lower()
        if (
            "just a moment" in body
            or "security verification" in body
            or "enable javascript and cookies" in body
        ):
            raise CloudflareChallenge() from exc
        raise SystemExit("HiringCafe API returned non-JSON data.") from exc


def load_session_state(session: Session, session_state_file: str) -> None:
    path = Path(session_state_file)
    if not path.exists():
        raise SystemExit(
            f"Session state file not found: {session_state_file}. "
            "Create it first with `uv run cafe-scout --export-session-state <path>`."
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"Session state file is not valid JSON: {session_state_file}") from exc

    cookies = _extract_session_cookies(payload)
    if not cookies:
        raise SystemExit(
            f"Session state file did not contain any cookies: {session_state_file}"
        )

    loaded = 0
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or cookie.get("host") or "").strip().lstrip(".")
        path_value = str(cookie.get("path") or "/")
        if not name or not value or not domain:
            continue
        if not hasattr(session, "_cf_cookies"):
            session._cf_cookies = {}  # type: ignore[attr-defined]
        session._cf_cookies[name] = value  # type: ignore[attr-defined]
        loaded += 1

    if not loaded:
        raise SystemExit(
            f"Session state file did not contain usable cookies: {session_state_file}"
        )


def _extract_session_cookies(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        cookies = payload.get("cookies")
        if isinstance(cookies, list):
            return [item for item in cookies if isinstance(item, dict)]
        if "name" in payload and "value" in payload:
            return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def build_locations(config: SearchConfig) -> list[dict[str, Any]]:
    if config.cities:
        return [build_city_location(city) for city in config.cities]
    if config.radius_city and config.radius_city in CITY_COORDS:
        return [build_city_location(config.radius_city, location_type="locality")]
    if config.allowed_countries:
        return [build_country_location(country) for country in config.allowed_countries]
    return []


def build_city_location(city: str, location_type: str = "locality") -> dict[str, Any]:
    coord = CITY_COORDS.get(city)
    geometry: dict[str, Any] = {}
    if coord:
        geometry = {"location": {"lat": coord[0], "lon": coord[1]}}
    return {
        "formatted_address": city,
        "types": [location_type],
        "geometry": geometry,
        "id": f"user_{location_type}_{city.casefold().replace(' ', '_')}",
        "address_components": [
            {
                "long_name": city,
                "short_name": city,
                "types": [location_type],
            }
        ],
        "options": {"flexible_regions": ["anywhere_in_continent", "anywhere_in_world"]},
    }


def build_country_location(country: str) -> dict[str, Any]:
    code = country.upper()
    label = COUNTRY_LABELS.get(code, country)
    if code == "DE":
        return {
            "id": "ZhY1yZQBoEtHp_8UEq3V",
            "types": ["country"],
            "address_components": [
                {
                    "long_name": "Germany",
                    "short_name": "DE",
                    "types": ["country"],
                }
            ],
            "formatted_address": "Germany",
            "population": 82927922,
            "workplace_types": [],
            "options": {"flexible_regions": ["anywhere_in_continent", "anywhere_in_world"]},
        }
    return {
        "formatted_address": label,
        "types": ["country"],
        "id": f"user_country_{code.lower()}",
        "address_components": [
            {
                "long_name": label,
                "short_name": code,
                "types": ["country"],
            }
        ],
        "workplace_types": [],
        "options": {"flexible_regions": ["anywhere_in_continent", "anywhere_in_world"]},
    }
