#!/usr/bin/env python3
"""
hiring.cafe job scraper

Server-side filters (encoded in the URL via ?searchState=):
  • seniorityLevel : Entry Level      → ~22 000 results vs 159 000 unfiltered
  • commitmentTypes: Full Time        → ~22 000 → ~22 000 (overlaps)
  • departments    : Software Dev + IT → ~22 000 → ~1 300 results (~13 pages)

Client-side filters (applied to each page's __NEXT_DATA__ hits):
  • Keywords  : .NET / C# / ASP.NET / TypeScript / React  (title + technical_tools)
  • Location  : Germany (DE) OR Remote-in-Europe/worldwide

Usage:
    uv run scraper.py          # run with the bundled venv
    python scraper.py          # if playwright is already installed globally
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ── Configuration ──────────────────────────────────────────────────────────────

KEYWORDS      = [".NET", "C#", "ASP.NET", "TypeScript", "React"]
BASE_URL      = "https://hiring.cafe"
OUTPUT        = "jobs.md"
SEEN_IDS_FILE = "seen_ids.txt"   # persists objectIDs across runs
MAX_PAGES     = 500              # safety ceiling — set to None to disable

# ── Location config (optional) ─────────────────────────────────────────────────
# CITIES    : only keep onsite/hybrid jobs in these cities. Empty = all of Germany.
#             e.g. ["Berlin", "Munich", "Hamburg"]
# RADIUS_KM : keep jobs within this distance from RADIUS_CITY (overrides CITIES).
#             Requires RADIUS_CITY to be set to a key in CITY_COORDS below.
#             e.g. RADIUS_KM = 50, RADIUS_CITY = "Berlin"
CITIES      = []
RADIUS_KM   = None
RADIUS_CITY = ""

CITY_COORDS = {
    "Berlin":     (52.520,  13.405),
    "Munich":     (48.137,  11.576),
    "Hamburg":    (53.551,   9.993),
    "Frankfurt":  (50.110,   8.682),
    "Cologne":    (50.938,   6.960),
    "Stuttgart":  (48.775,   9.182),
    "Düsseldorf": (51.227,   6.773),
    "Leipzig":    (51.340,  12.375),
    "Dortmund":   (51.514,   7.465),
    "Dresden":    (51.050,  13.737),
    "Hannover":   (52.374,   9.738),
    "Nuremberg":  (49.453,  11.077),
    "Bremen":     (53.075,   8.807),
}

# Encoded once at import time; hiring.cafe applies these server-side.
# "Software Development" + "Information Technology" together cover both common
# classifications for .NET / C# / TypeScript / React developer roles.
_SEARCH_STATE = quote(json.dumps({
    "seniorityLevel":  ["Entry Level"],
    "commitmentTypes": ["Full Time"],
    "departments":     ["Software Development", "Information Technology", "Engineering"],
}))

# Seniority values to EXCLUDE (everything else is kept, including blank)
SENIOR_LEVELS = {"senior level", "mid level", "lead", "principal", "staff", "manager"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


# ── Seen-IDs tracking ──────────────────────────────────────────────────────────

def load_seen_ids() -> set[str]:
    p = Path(SEEN_IDS_FILE)
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text().splitlines() if line.strip()}


def save_seen_ids(new_ids: list[str]) -> None:
    with open(SEEN_IDS_FILE, "a", encoding="utf-8") as f:
        for oid in new_ids:
            f.write(oid + "\n")


# ── Filters ────────────────────────────────────────────────────────────────────

def _matches_keyword(hit: dict) -> bool:
    v5 = hit.get("v5_processed_job_data") or {}
    ji = hit.get("job_information") or {}
    title   = (v5.get("core_job_title") or ji.get("title") or "").lower()
    tools   = " ".join(v5.get("technical_tools") or []).lower()
    summary = (v5.get("requirements_summary") or "").lower()
    return any(kw.lower() in f"{title} {tools} {summary}" for kw in KEYWORDS)


def _matches_seniority(hit: dict) -> bool:
    v5 = hit.get("v5_processed_job_data") or {}
    seniority = (v5.get("seniority_level") or "").lower().strip()
    # Blank seniority = unspecified; keep it (many junior postings omit level)
    if not seniority:
        return True
    # Explicitly junior / entry
    if any(s in seniority for s in ("entry", "junior", "associate", "intern", "graduate")):
        return True
    # Explicitly senior / mid → drop
    return not any(s in seniority for s in SENIOR_LEVELS)


def _matches_commitment(hit: dict) -> bool:
    v5 = hit.get("v5_processed_job_data") or {}
    commitment = v5.get("commitment") or []
    if isinstance(commitment, list):
        return any("full" in c.lower() for c in commitment)
    return "full" in str(commitment).lower()


def _matches_location(hit: dict) -> bool:
    v5  = hit.get("v5_processed_job_data") or {}
    wt  = (v5.get("workplace_type") or "").lower()

    # Remote jobs: keep if European or worldwide scope (unaffected by city/radius)
    if "remote" in wt:
        continents = (
            (v5.get("workplace_continents") or [])
            + (v5.get("boundless_workplace_continents") or [])
        )
        if "Europe" in continents or v5.get("is_workplace_worldwide_ok"):
            return True

    # Onsite / hybrid: must be in Germany
    if "DE" not in (v5.get("workplace_countries") or []):
        return False

    # No extra city/radius filter → accept all German jobs
    if not CITIES and not (RADIUS_KM and RADIUS_CITY):
        return True

    job_cities  = v5.get("workplace_cities") or []     # ["Berlin, Berlin, DE", ...]
    job_geolocations = hit.get("_geoloc") or []        # [{"lat": 52.52, "lon": 13.41}, ...]

    # Radius filter (takes priority over city list)
    if RADIUS_KM and RADIUS_CITY and RADIUS_CITY in CITY_COORDS:
        tlat, tlon = CITY_COORDS[RADIUS_CITY]
        for geo in job_geolocations:
            if _haversine_km(tlat, tlon, geo["lat"], geo["lon"]) <= RADIUS_KM:
                return True
        return False

    # City name filter
    for city in job_cities:
        if any(c.lower() in city.lower() for c in CITIES):
            return True
    return False


# ── Extraction ─────────────────────────────────────────────────────────────────

def _extract(hit: dict, url: str) -> dict:
    v5 = hit.get("v5_processed_job_data") or {}
    ji = hit.get("job_information") or {}
    cd = hit.get("enriched_company_data") or {}

    title = (
        v5.get("core_job_title")
        or re.sub(r"\s*\([^)]*\)", "", ji.get("title") or "").strip()
        or "Unknown"
    )
    company    = cd.get("name") or v5.get("company_name") or "Unknown"
    location   = v5.get("formatted_workplace_location") or "Unknown"
    work_type  = v5.get("workplace_type") or ""
    commitment_raw = v5.get("commitment") or []
    commitment = (
        commitment_raw[0]
        if isinstance(commitment_raw, list) and commitment_raw
        else str(commitment_raw)
    )

    ts = v5.get("estimated_publish_date_millis")
    if ts:
        date_obj   = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        posted_str = date_obj.strftime("%Y-%m-%d")
    else:
        date_obj   = datetime.min.replace(tzinfo=timezone.utc)
        posted_str = v5.get("estimated_publish_date") or "Unknown"

    return {
        "object_id": hit.get("objectID") or hit.get("id") or "",
        "title": title, "company": company,
        "location": location, "work_type": work_type,
        "commitment": commitment, "url": url,
        "apply_url": hit.get("apply_url") or "",
        "posted_str": posted_str, "date_obj": date_obj,
    }


# ── Page loading ───────────────────────────────────────────────────────────────

async def _load_page(page, url: str, retries: int = 3):
    """Return (pageProps dict, list of job URLs) or (None, []) on failure."""
    for attempt in range(retries):
        try:
            strategy = "networkidle" if attempt == 0 else "domcontentloaded"
            await page.goto(url, wait_until=strategy, timeout=30_000)

            # Scroll to trigger any deferred rendering
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(400)

            job_urls = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href^="/job/"]'))
                          .map(a => a.href)
            """)

            props = await page.evaluate("""
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    if (!el) return null;
                    const d = JSON.parse(el.textContent);
                    return d?.props?.pageProps ?? null;
                }
            """)

            if props and job_urls:
                return props, job_urls

        except PlaywrightTimeout:
            print(f"  timeout (attempt {attempt + 1}/{retries})", file=sys.stderr)
        except Exception as exc:
            print(f"  error: {exc}", file=sys.stderr)

    return None, []


# ── Main scraper ───────────────────────────────────────────────────────────────

async def scrape(seen_ids: set[str]) -> list[dict]:
    all_jobs: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        pg = await ctx.new_page()

        page_num = 0
        while MAX_PAGES is None or page_num < MAX_PAGES:
            # searchState encodes Entry Level + Full Time filters server-side
            url = f"{BASE_URL}/?searchState={_SEARCH_STATE}&page={page_num}"
            print(f"  page {page_num + 1:>4} …", end=" ", flush=True)

            props, job_urls = await _load_page(pg, url)
            if not props:
                print("FAILED — stopping.", file=sys.stderr)
                break

            if page_num == 0:
                total = props.get("ssrTotalCount", "?")
                print(f"({total} server-filtered listings)")

            hits = props.get("ssrHits") or []
            matched = skipped = 0
            for i, hit in enumerate(hits):
                oid = hit.get("objectID") or hit.get("id") or ""
                if oid and oid in seen_ids:
                    skipped += 1
                    continue
                if not (_matches_location(hit)
                        and _matches_seniority(hit)
                        and _matches_commitment(hit)
                        and _matches_keyword(hit)):
                    continue
                hit_url = job_urls[i] if i < len(job_urls) else ""
                all_jobs.append(_extract(hit, hit_url))
                matched += 1

            skip_str = f", {skipped} already seen" if skipped else ""
            print(f"{len(hits):>3} listings → {matched} matched{skip_str}")

            if props.get("ssrIsLastPage"):
                print("  last page reached.")
                break

            page_num += 1

        await browser.close()

    return all_jobs


# ── Output ─────────────────────────────────────────────────────────────────────

def save_markdown(jobs: list[dict]) -> None:
    jobs.sort(key=lambda j: j["date_obj"], reverse=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Job Listings — hiring.cafe",
        "",
        f"**Keywords:** {' / '.join(KEYWORDS)}  ",
        "**Location:** Germany + Remote Europe  ",
        "**Level:** Junior / Entry  ",
        "**Commitment:** Full Time  ",
        f"**Scraped:** {now_str}  ",
        f"**Total matches:** {len(jobs)}",
        "",
        "---",
        "",
    ]

    for i, j in enumerate(jobs, 1):
        wt        = " · ".join(filter(None, [j["work_type"], j["commitment"]]))
        apply     = f" | Apply: {j['apply_url']}" if j["apply_url"] else ""
        lines.append(
            f"{i}. {j['company']} — {j['title']} | {j['location']} | "
            f"{wt} | {j['posted_str']} | {j['url']}{apply}"
        )

    Path(OUTPUT).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved {len(jobs)} jobs → {OUTPUT}")


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    print("hiring.cafe scraper")
    print(f"  keywords : {', '.join(KEYWORDS)}")
    print(f"  location : Germany + Remote Europe")
    print(f"  level    : Junior / Entry")
    print(f"  type     : Full Time")

    seen_ids = load_seen_ids()
    if seen_ids:
        print(f"  skipping : {len(seen_ids)} previously seen jobs")
    print()

    jobs = await scrape(seen_ids)

    if not jobs:
        print("No new matching jobs found.")
        return

    save_markdown(jobs)

    new_ids = [j["object_id"] for j in jobs if j["object_id"]]
    save_seen_ids(new_ids)
    print(f"Recorded {len(new_ids)} new IDs → {SEEN_IDS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
