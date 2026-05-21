from __future__ import annotations

import asyncio

from job_parser.api import (
    PAGE_SIZE,
    CloudflareChallenge,
    build_search_state,
    build_session,
    fetch_jobs_page,
    fetch_total_count,
)
from job_parser.browser_scraper import scrape_with_browser
from job_parser.config import SearchConfig, is_senior_scope, load_seen_ids, save_seen_ids
from job_parser.exporters.json import save_json
from job_parser.exporters.markdown import save_markdown
from job_parser.filters import (
    matches_commitment,
    matches_keyword,
    matches_location,
    matches_seniority_configured,
)
from job_parser.models import Job
from job_parser.payload import parse_job


async def run(config: SearchConfig | None = None) -> None:
    active_config = config or SearchConfig()
    if not active_config.seniority_terms:
        seniority_display = "All"
    else:
        seniority_display = "Senior" if is_senior_scope(active_config) else "Others"
    location_parts = [", ".join(active_config.allowed_countries) or "Anywhere"]
    if active_config.cities:
        location_parts.append(f"cities={', '.join(active_config.cities)}")
    if active_config.radius_km and active_config.radius_city:
        location_parts.append(
            f"radius={active_config.radius_km}km around {active_config.radius_city}"
        )

    print("hiring.cafe scraper")
    print(f"  keywords : {', '.join(active_config.keywords)}")
    print(f"  location : {' | '.join(location_parts)}")
    print(f"  level    : {seniority_display}")
    print(f"  type     : {', '.join(active_config.commitments) if active_config.commitments else 'Any'}")
    print(
        f"  session  : {active_config.session_state_file or 'none'}"
    )
    print(f"  browser  : {active_config.browser_profile_dir or 'none'}")

    seen_ids = set()
    if not active_config.include_seen:
        seen_ids = load_seen_ids(active_config.seen_ids_file)
    if seen_ids:
        print(f"  skipping : {len(seen_ids)} previously seen jobs")
    print()

    jobs = await scrape(active_config, seen_ids)
    if not jobs:
        print("No new matching jobs found.")
        return

    if active_config.export_markdown:
        save_markdown(jobs, active_config)
        print(f"\nSaved {len(jobs)} jobs → {active_config.markdown_output}")
    if active_config.export_json:
        save_json(jobs, active_config)
        print(f"Saved {len(jobs)} jobs → {active_config.json_output}")

    new_ids = [job.object_id for job in jobs if job.object_id]
    if not active_config.include_seen:
        save_seen_ids(active_config.seen_ids_file, new_ids)
        print(f"Recorded {len(new_ids)} new IDs → {active_config.seen_ids_file}")


async def scrape(config: SearchConfig, seen_ids: set[str]) -> list[Job]:
    url_mode = bool(config.search_url.strip())
    browser_profile_dir = config.browser_profile_dir.strip() or None
    if url_mode or browser_profile_dir:
        return await asyncio.to_thread(
            scrape_with_browser,
            config,
            seen_ids,
            profile_dir=browser_profile_dir,
            apply_local_filters=not url_mode,
        )

    all_jobs: list[Job] = []
    search_state = build_search_state(config)
    session = build_session(config)

    try:
        try:
            total_count = await asyncio.to_thread(fetch_total_count, config, search_state, session)
        except CloudflareChallenge:
            print(
                "Cloudflare blocked the direct API path. "
                "Switching to browser-context requests in a visible Chromium browser..."
            )
            session.close()
            return await asyncio.to_thread(
                scrape_with_browser,
                config,
                seen_ids,
                profile_dir=browser_profile_dir,
                apply_local_filters=not url_mode,
            )

        page_num = 0
        while config.max_pages is None or page_num < config.max_pages:
            print(f"  page {page_num + 1:>4} …", end=" ", flush=True)

            try:
                raw_hits = await asyncio.to_thread(
                    fetch_jobs_page,
                    config,
                    search_state,
                    page_num,
                    PAGE_SIZE,
                    session,
                )
            except CloudflareChallenge:
                raise SystemExit(
                    "Cloudflare re-blocked mid-scrape. "
                    "Re-run cafe-scout to solve the challenge again."
                )

            if page_num == 0:
                total = total_count if total_count is not None else "?"
                print(f"({total} api listings)")

            if not raw_hits:
                print("0 listings → 0 matched")
                break

            matched = 0
            skipped = 0
            for hit in raw_hits:
                object_id = hit.get("objectID") or hit.get("id") or ""
                if object_id and object_id in seen_ids:
                    skipped += 1
                    continue

                job_url = hit.get("job_url") or hit.get("url") or hit.get("application_url") or ""
                job = parse_job(hit, str(job_url))
                if not url_mode and not (
                    matches_location(job, config)
                    and matches_seniority_configured(job, config)
                    and matches_commitment(job, config)
                    and matches_keyword(job, config)
                ):
                    continue

                all_jobs.append(job)
                matched += 1

            skip_suffix = f", {skipped} already seen" if skipped else ""
            print(f"{len(raw_hits):>3} listings → {matched} matched{skip_suffix}")

            if len(raw_hits) < PAGE_SIZE:
                print("  last page reached.")
                break

            page_num += 1
    finally:
        session.close()

    return all_jobs
