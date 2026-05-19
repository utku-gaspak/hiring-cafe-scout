from __future__ import annotations

import asyncio
import sys

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from job_parser.config import (
    SERVER_FILTER_SEARCH_STATE,
    SearchConfig,
    load_seen_ids,
    save_seen_ids,
)
from job_parser.exporters.json import save_json
from job_parser.exporters.markdown import save_markdown
from job_parser.filters import (
    matches_commitment,
    matches_keyword,
    matches_location,
    matches_seniority,
)
from job_parser.models import Job
from job_parser.payload import parse_job


async def run(config: SearchConfig | None = None) -> None:
    active_config = config or SearchConfig()

    print("hiring.cafe scraper")
    print(f"  keywords : {', '.join(active_config.keywords)}")
    print("  location : Germany + Remote Europe")
    print("  level    : Junior / Entry")
    print("  type     : Full Time")

    seen_ids = load_seen_ids(active_config.seen_ids_file)
    if seen_ids:
        print(f"  skipping : {len(seen_ids)} previously seen jobs")
    print()

    jobs = await scrape(active_config, seen_ids)
    if not jobs:
        print("No new matching jobs found.")
        return

    save_markdown(jobs, active_config)
    save_json(jobs, active_config)
    print(f"\nSaved {len(jobs)} jobs → {active_config.markdown_output}")
    print(f"Saved {len(jobs)} jobs → {active_config.json_output}")

    new_ids = [job.object_id for job in jobs if job.object_id]
    save_seen_ids(active_config.seen_ids_file, new_ids)
    print(f"Recorded {len(new_ids)} new IDs → {active_config.seen_ids_file}")


async def scrape(config: SearchConfig, seen_ids: set[str]) -> list[Job]:
    all_jobs: list[Job] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        page_num = 0
        while config.max_pages is None or page_num < config.max_pages:
            url = f"{config.base_url}/?searchState={SERVER_FILTER_SEARCH_STATE}&page={page_num}"
            print(f"  page {page_num + 1:>4} …", end=" ", flush=True)

            page_props, job_urls = await load_page(page, url)
            if not page_props:
                print("FAILED — stopping.", file=sys.stderr)
                break

            if page_num == 0:
                total = page_props.get("ssrTotalCount", "?")
                print(f"({total} server-filtered listings)")

            hits = page_props.get("ssrHits") or []
            matched = 0
            skipped = 0
            for index, hit in enumerate(hits):
                object_id = hit.get("objectID") or hit.get("id") or ""
                if object_id and object_id in seen_ids:
                    skipped += 1
                    continue

                hit_url = job_urls[index] if index < len(job_urls) else ""
                job = parse_job(hit, hit_url)
                if not (
                    matches_location(job, config)
                    and matches_seniority(job)
                    and matches_commitment(job)
                    and matches_keyword(job, config)
                ):
                    continue

                all_jobs.append(job)
                matched += 1

            skip_suffix = f", {skipped} already seen" if skipped else ""
            print(f"{len(hits):>3} listings → {matched} matched{skip_suffix}")

            if page_props.get("ssrIsLastPage"):
                print("  last page reached.")
                break

            page_num += 1

        await browser.close()

    return all_jobs


async def load_page(page, url: str, retries: int = 3) -> tuple[dict | None, list[str]]:
    for attempt in range(retries):
        try:
            wait_strategy = "networkidle" if attempt == 0 else "domcontentloaded"
            await page.goto(url, wait_until=wait_strategy, timeout=30_000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(400)

            job_urls = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a[href^="/job/"]'))
                          .map(a => a.href)
                """
            )

            page_props = await page.evaluate(
                """
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    if (!el) return null;
                    const d = JSON.parse(el.textContent);
                    return d?.props?.pageProps ?? null;
                }
                """
            )

            if page_props and job_urls:
                return page_props, job_urls
        except PlaywrightTimeout:
            print(f"  timeout (attempt {attempt + 1}/{retries})", file=sys.stderr)
        except Exception as exc:
            print(f"  error: {exc}", file=sys.stderr)

    return None, []


def main() -> None:
    asyncio.run(run())
