from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from job_parser.config import SearchConfig
from job_parser.filters import (
    matches_commitment,
    matches_location,
    matches_seniority_configured,
)
from job_parser.models import Job


class CloudflareVerificationRequired(Exception):
    """Raised when the browser reaches a Cloudflare challenge page."""


def scrape_with_browser(
    config: SearchConfig,
    seen_ids: set[str],
    profile_dir: str | None = None,
    apply_local_filters: bool = True,
) -> list[Job]:
    try:
        from pydoll.browser.chromium import Chrome
        from pydoll.browser.options import ChromiumOptions
        from pydoll.constants import PageLoadState
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise SystemExit(
            "Missing dependency: pydoll-python\n"
            "Install it with `uv sync` and then rerun cafe-scout."
        ) from exc

    return asyncio.run(
        _scrape_with_browser(
            Chrome=Chrome,
            ChromiumOptions=ChromiumOptions,
            PageLoadState=PageLoadState,
            config=config,
            seen_ids=seen_ids,
            profile_dir=profile_dir,
            apply_local_filters=apply_local_filters,
        )
    )


def _debug_enabled() -> bool:
    return os.environ.get("CAFE_SCOUT_DEBUG_BROWSER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _debug(message: str) -> None:
    if _debug_enabled():
        print(f"    debug: {message}")


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def _scrape_with_browser(
    *,
    Chrome: Any,
    ChromiumOptions: Any,
    PageLoadState: Any,
    config: SearchConfig,
    seen_ids: set[str],
    profile_dir: str | None,
    apply_local_filters: bool,
) -> list[Job]:
    all_jobs: list[Job] = []
    headless = _env_enabled("CAFE_SCOUT_HEADLESS")
    options = _build_browser_options(
        ChromiumOptions=ChromiumOptions,
        PageLoadState=PageLoadState,
        profile_dir=profile_dir,
    )
    search_state = _build_search_state(config)
    search_url = _build_search_url(config, search_state)

    browser = Chrome(options=options)
    try:
        try:
            tab = await browser.start()
        except Exception as exc:
            raise SystemExit(
                "Pydoll could not start Chromium.\n"
                f"Binary: {options.binary_location}\n"
                "Try setting CAFE_SCOUT_BROWSER_BINARY to a different Chrome/Chromium binary, "
                "or install Playwright Chromium with `uv run playwright install chromium`.\n"
                f"Underlying error: {exc}"
            ) from exc
        initial_url = search_url if config.search_url.strip() else config.base_url
        _debug(f"initial navigation to {initial_url}")
        await tab.go_to(initial_url)
        if await _looks_like_challenge(tab):
            _write_needs_verification_progress(
                config=config,
                pages_scraped=0,
                visible_jobs_scraped=0,
                matched_jobs=0,
                current_page_listings=0,
                current_page_matched=0,
                skipped_seen=0,
            )
            if headless:
                raise SystemExit(
                    "Cloudflare challenge detected. Verification required in a visible browser session."
                )
            print("Cloudflare challenge detected. Solve it in the browser window.")
            await asyncio.to_thread(input, "Press Enter once the browser is usable: ")
            await asyncio.sleep(1)
        else:
            print("Browser loaded.")

        page_num = 0
        extracted_count = 0
        while config.max_pages is None or page_num < config.max_pages:
            print(f"  page {page_num + 1:>4} …", end=" ", flush=True)

            try:
                page_data = await _browser_fetch_search_page(tab, search_url, page_num)
            except CloudflareVerificationRequired as exc:
                _write_needs_verification_progress(
                    config=config,
                    pages_scraped=page_num,
                    visible_jobs_scraped=extracted_count,
                    matched_jobs=len(all_jobs),
                    current_page_listings=0,
                    current_page_matched=0,
                    skipped_seen=0,
                )
                raise SystemExit(
                    "Cloudflare challenge detected. Verification required in a visible browser session."
                ) from exc
            if page_num == 0:
                total_display = page_data["total_count"] if page_data["total_count"] is not None else "?"
                print(f"({total_display} total jobs visible on this page)")

            if not page_data["cards"]:
                _write_progress(
                    config,
                    _build_progress_payload(
                        status="done",
                        pages_scraped=page_num + 1,
                        visible_jobs_scraped=extracted_count,
                        matched_jobs=len(all_jobs),
                        estimated_total_jobs=page_data["total_count"],
                        current_page_listings=0,
                        current_page_matched=0,
                        skipped_seen=0,
                        message="No more visible listings",
                    ),
                )
                print("0 listings → 0 matched")
                break

            matched = 0
            skipped = 0
            for card in page_data["cards"]:
                object_id = card["url"] or f"{card['title']}|{card['location']}"
                if object_id in seen_ids:
                    skipped += 1
                    continue

                job = _build_job_from_card(card)
                if apply_local_filters and not (
                    matches_location(job, config)
                    and matches_seniority_configured(job, config)
                    and matches_commitment(job, config)
                ):
                    continue

                all_jobs.append(job)
                matched += 1

            skip_suffix = f", {skipped} already seen" if skipped else ""
            print(f"{len(page_data['cards']):>3} listings → {matched} matched{skip_suffix}")

            extracted_count += page_data["job_count"]
            _write_progress(
                config,
                _build_progress_payload(
                    status="running",
                    pages_scraped=page_num + 1,
                    visible_jobs_scraped=extracted_count,
                    matched_jobs=len(all_jobs),
                    estimated_total_jobs=page_data["total_count"],
                    current_page_listings=page_data["job_count"],
                    current_page_matched=matched,
                    skipped_seen=skipped,
                    message=f"Scraped page {page_num + 1}",
                ),
            )
            if page_data["total_count"] is not None and extracted_count < page_data["total_count"]:
                page_num += 1
                continue

            if not await _has_next_page(tab, page_num + 1):
                _write_progress(
                    config,
                    _build_progress_payload(
                        status="done",
                        pages_scraped=page_num + 1,
                        visible_jobs_scraped=extracted_count,
                        matched_jobs=len(all_jobs),
                        estimated_total_jobs=page_data["total_count"],
                        current_page_listings=page_data["job_count"],
                        current_page_matched=matched,
                        skipped_seen=skipped,
                        message="Last page reached",
                    ),
                )
                print("  last page reached.")
                break

            page_num += 1

    finally:
        await _close_browser_safely(browser)

    return all_jobs


async def _close_browser_safely(browser: Any) -> None:
    with contextlib.suppress(Exception):
        await browser.stop()
        return
    with contextlib.suppress(Exception):
        await browser.close()


def _build_browser_options(*, ChromiumOptions: Any, PageLoadState: Any, profile_dir: str | None) -> Any:
    options = ChromiumOptions()
    headless = _env_enabled("CAFE_SCOUT_HEADLESS")
    options.headless = headless
    binary_location = _find_browser_binary()
    if not binary_location:
        raise SystemExit(
            "No Chromium/Chrome binary found for Pydoll.\n"
            "Install one of these or point CAFE_SCOUT_BROWSER_BINARY at it:\n"
            "  - a system Chrome/Chromium binary\n"
            "  - `uv run playwright install chromium`"
        )
    with contextlib.suppress(Exception):
        options.binary_location = binary_location
    with contextlib.suppress(Exception):
        options.start_timeout = 30
    with contextlib.suppress(Exception):
        options.page_load_state = PageLoadState.INTERACTIVE
    with contextlib.suppress(Exception):
        options.block_notifications = True
    with contextlib.suppress(Exception):
        options.block_popups = True

    for argument in (
        "--disable-blink-features=AutomationControlled",
        "--window-size=1920,1080",
        "--lang=en-US",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    ):
        with contextlib.suppress(Exception):
            options.add_argument(argument)

    if headless:
        with contextlib.suppress(Exception):
            options.add_argument("--headless=new")

    with contextlib.suppress(Exception):
        options.set_accept_languages("en-US,en;q=0.9")

    if profile_dir and profile_dir.strip():
        profile_path = Path(profile_dir).expanduser()
        profile_path.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            options.add_argument(f"--user-data-dir={profile_path}")

    return options


def _find_browser_binary() -> str | None:
    override = os.environ.get("CAFE_SCOUT_BROWSER_BINARY", "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    candidates = [
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/brave"),
        Path("/usr/bin/brave-browser"),
    ]
    candidates.extend(_playwright_chromium_binaries())

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _playwright_chromium_binaries() -> list[Path]:
    roots = [
        Path.home() / ".cache" / "ms-playwright",
        Path.home() / ".local" / "share" / "ms-playwright",
    ]
    matches: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        matches.extend(sorted(root.glob("chromium-*/chrome-linux64/chrome")))
        matches.extend(sorted(root.glob("chromium-*/chrome-linux/chrome")))
    return matches


async def _looks_like_challenge(tab: Any) -> bool:
    with contextlib.suppress(Exception):
        title = _script_value(await tab.execute_script("return JSON.stringify(document.title)"))
        if "just a moment" in title.lower() or "cloudflare" in title.lower():
            return True
    with contextlib.suppress(Exception):
        body = _script_value(
            await tab.execute_script(
                "return JSON.stringify(document.body ? document.body.innerText : '')"
            )
        )
        if "just a moment" in body.lower() or "enable javascript and cookies" in body.lower():
            return True
    return False


async def _browser_fetch_search_page(tab: Any, search_url: str, page_num: int) -> dict[str, Any]:
    if page_num:
        page_url = f"{search_url}{'&' if '?' in search_url else '?'}page={page_num}"
    else:
        page_url = search_url
    _debug(f"navigating to {page_url}")
    await tab.go_to(page_url)
    if await _looks_like_challenge(tab):
        raise CloudflareVerificationRequired()

    body_text = await _wait_for_search_body(tab)
    current_url = await _read_current_url(tab)
    total_count = _extract_total_job_count(body_text)
    card_blocks = await _extract_card_blocks(tab)
    if card_blocks:
        cards = [_parse_card_block(block["text"], block["url"]) for block in card_blocks]
        cards = [card for card in cards if card]
    else:
        cards = []
    if not cards:
        job_links = _script_value(
            await tab.execute_script(
                """
                return JSON.stringify(Array.from(document.querySelectorAll('a'))
                  .filter(a => (a.innerText || '').trim() === 'Job Posting')
                  .map(a => a.href));
                """
            )
        )
        cards = _parse_job_cards(body_text, job_links)
    link_count = await _count_page_links(tab)
    _debug(
        "page metrics: "
        f"current_url={current_url}, body_chars={len(body_text)}, "
        f"total_count={total_count}, card_blocks={len(card_blocks)}, "
        f"cards={len(cards)}, page_links={link_count}"
    )
    return {
        "cards": cards,
        "job_count": len(cards),
        "total_count": total_count,
        "current_url": current_url,
        "page_url": page_url,
        "page_link_count": link_count,
    }


async def _wait_for_search_body(tab: Any, timeout_seconds: float = 10.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_body = ""
    while time.monotonic() < deadline:
        last_body = await _read_page_text(tab)
        if _looks_ready_for_parsing(last_body):
            return last_body
        await asyncio.sleep(0.5)
    return last_body


async def _read_page_text(tab: Any) -> str:
    with contextlib.suppress(Exception):
        body_text = _script_value(
            await tab.execute_script(
                """
                return JSON.stringify(
                  document.body
                    ? (document.body.innerText || document.documentElement.innerText || '')
                    : (document.documentElement ? document.documentElement.innerText : '')
                );
                """
            )
        )
        return body_text
    return ""


async def _read_current_url(tab: Any) -> str:
    with contextlib.suppress(Exception):
        url = _script_value(await tab.execute_script("return JSON.stringify(location.href)"))
        return str(url)
    return ""


async def _count_page_links(tab: Any) -> int:
    with contextlib.suppress(Exception):
        links = _script_value(
            await tab.execute_script(
                """
                return JSON.stringify(Array.from(document.querySelectorAll('a[href]'))
                  .filter(a => new URL(a.href).searchParams.has('page'))
                  .map(a => a.href));
                """
            )
        )
        if isinstance(links, list):
            return len(links)
    return 0


def _looks_ready_for_parsing(body_text: str) -> bool:
    lowered = body_text.lower()
    return (
        "job posting" in lowered
        or "mark applied" in lowered
        or "no jobs" in lowered
        or "0 jobs" in lowered
    )


def _extract_total_job_count(body_text: str) -> int | None:
    match = re.search(r"(\d[\d,]*)\s+jobs?\b", body_text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _build_progress_payload(
    *,
    status: str,
    pages_scraped: int,
    visible_jobs_scraped: int,
    matched_jobs: int,
    estimated_total_jobs: int | None,
    current_page_listings: int,
    current_page_matched: int,
    skipped_seen: int,
    message: str,
) -> dict[str, object]:
    progress_percent: int | None = None
    if status == "done":
        progress_percent = 100
    elif estimated_total_jobs and estimated_total_jobs > 0:
        progress_percent = min(round((visible_jobs_scraped / estimated_total_jobs) * 100), 99)

    return {
        "status": status,
        "pages_scraped": pages_scraped,
        "visible_jobs_scraped": visible_jobs_scraped,
        "matched_jobs": matched_jobs,
        "estimated_total_jobs": estimated_total_jobs,
        "total_is_estimate": estimated_total_jobs is not None,
        "progress_percent": progress_percent,
        "current_page_listings": current_page_listings,
        "current_page_matched": current_page_matched,
        "skipped_seen": skipped_seen,
        "message": message,
    }


def _write_needs_verification_progress(
    *,
    config: SearchConfig,
    pages_scraped: int,
    visible_jobs_scraped: int,
    matched_jobs: int,
    current_page_listings: int,
    current_page_matched: int,
    skipped_seen: int,
) -> None:
    _write_progress(
        config,
        _build_progress_payload(
            status="needs_verification",
            pages_scraped=pages_scraped,
            visible_jobs_scraped=visible_jobs_scraped,
            matched_jobs=matched_jobs,
            estimated_total_jobs=None,
            current_page_listings=current_page_listings,
            current_page_matched=current_page_matched,
            skipped_seen=skipped_seen,
            message="Cloudflare challenge detected",
        ),
    )


def _write_progress(config: SearchConfig, payload: dict[str, object]) -> None:
    if not config.progress_output.strip():
        return
    progress_path = Path(config.progress_output).expanduser()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


async def _extract_card_blocks(tab: Any) -> list[dict[str, str]]:
    script = """
    const blocks = [];
    const seen = new Set();
    const anchors = Array.from(document.querySelectorAll('a'))
      .filter(a => (a.innerText || '').trim() === 'Job Posting');

    for (const anchor of anchors) {
      const container =
        anchor.closest('article, li, section, [role="article"]') ||
        anchor.parentElement?.parentElement ||
        anchor.parentElement;
      if (!container) continue;

      const text = (container.innerText || '').trim();
      const href = anchor.href || '';
      const key = `${href}::${text}`;
      if (!text || seen.has(key)) continue;
      seen.add(key);
      blocks.push({ text, url: href });
    }
    return JSON.stringify(blocks);
    """
    with contextlib.suppress(Exception):
        result = _script_value(await tab.execute_script(script))
        if isinstance(result, list):
            return [
                {"text": str(item.get("text") or ""), "url": str(item.get("url") or "")}
                for item in result
                if isinstance(item, dict) and str(item.get("text") or "").strip()
            ]
    return []


async def _has_next_page(tab: Any, next_page_num: int) -> bool:
    page_links = _script_value(
        await tab.execute_script(
            """
            return JSON.stringify(Array.from(document.querySelectorAll('a[href]'))
              .map(a => a.href));
            """
        )
    )
    if not isinstance(page_links, list):
        return False
    for link in page_links:
        if _href_targets_page(str(link), next_page_num):
            return True
    return False


def _build_search_state(config: SearchConfig) -> str:
    from job_parser.config import build_search_state as build_browser_search_state

    return build_browser_search_state(config)


def _build_search_url(config: SearchConfig, search_state: str) -> str:
    if config.search_url.strip():
        return config.search_url.strip()
    base = config.base_url.rstrip("/")
    if not search_state:
        return base
    return f"{base}/?searchState={search_state}"


def _href_targets_page(href: str, next_page_num: int) -> bool:
    if not href:
        return False
    try:
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(href).query)
    except Exception:
        return False
    page_values = query.get("page", [])
    return any(str(value) == str(next_page_num) for value in page_values)


def _unwrap_script_result(value: Any) -> Any:
    current = value
    while isinstance(current, dict):
        if "result" in current:
            current = current["result"]
            continue
        if set(current.keys()) <= {"type", "value"} and "value" in current:
            current = current["value"]
            continue
        break
    return current


def _script_value(value: Any) -> Any:
    current = _unwrap_script_result(value)
    if isinstance(current, str):
        try:
            return json.loads(current)
        except ValueError:
            return current
    return current


def _parse_job_cards(body_text: str, job_links: list[str] | tuple[str, ...] | Any) -> list[dict[str, str]]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in body_text.splitlines()]
    lines = [line for line in lines if line]
    title_indexes = [
        index
        for index in range(len(lines) - 2)
        if _looks_like_title_line(lines[index])
        and _looks_like_location_line(lines[index + 1])
        and _looks_like_work_line(lines[index + 2])
    ]
    if not title_indexes:
        return []

    cards: list[dict[str, str]] = []
    for idx, title_index in enumerate(title_indexes):
        next_title = title_indexes[idx + 1] if idx + 1 < len(title_indexes) else len(lines)
        block = lines[title_index:next_title]
        card = _parse_block(block)
        if card:
            cards.append(card)

    if isinstance(job_links, (list, tuple)):
        parsed_links = [str(link) for link in job_links if str(link).strip()]
        for card, link in zip(cards, parsed_links, strict=False):
            card["url"] = link
            card["object_id"] = link

    return cards


def _parse_card_block(text: str, url: str) -> dict[str, str] | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    card = _parse_block(lines)
    if not card:
        return None
    card["url"] = url
    card["object_id"] = url
    return card


def _parse_block(lines: list[str]) -> dict[str, str] | None:
    if len(lines) < 3:
        return None
    title = lines[0]
    location = lines[1]
    work_line = lines[2]

    company = ""
    summary = ""
    tools = ""
    seniority = ""
    for line in lines[3:]:
        if not company:
            if line.startswith("Image: "):
                company = line.removeprefix("Image: ").split(":", 1)[0].strip()
                continue
            if ": " in line and not _looks_like_meta_line(line):
                company = line.split(":", 1)[0].strip()
                if not summary:
                    summary = line.split(":", 1)[1].strip()
                continue
        if not seniority and _looks_like_senior_line(line):
            seniority = "Senior Level"
        if not summary and _looks_like_summary_line(line):
            summary = line
            continue
        if not tools and _looks_like_tools_line(line):
            tools = line
            continue

    work_type, commitment = _parse_work_and_commitment(work_line)
    return {
        "object_id": "",
        "url": "",
        "title": title,
        "location": location,
        "work_type": work_type,
        "commitment": commitment,
        "company": company or "Unknown",
        "summary": summary,
        "tools": tools,
        "seniority": seniority,
    }


def _build_job_from_card(card: dict[str, str]) -> Job:
    location = card.get("location") or "Unknown"
    location_parts = [part.strip() for part in location.split(",") if part.strip()]
    cities = [location_parts[0]] if location_parts else []
    countries = [location_parts[-1]] if len(location_parts) > 1 else []
    commitment = card.get("commitment") or ""
    work_type = card.get("work_type") or ""
    technical_tools = _split_tools(card.get("tools") or "")
    seniority_level = card.get("seniority") or ""

    return Job(
        object_id=card.get("object_id") or card.get("url") or f"{card.get('title')}|{location}",
        source="hiring.cafe",
        title=card.get("title") or "Unknown",
        raw_title=card.get("title") or "Unknown",
        company=card.get("company") or "Unknown",
        location=location,
        work_type=work_type,
        commitment=commitment,
        commitments=[commitment] if commitment else [],
        cities=cities,
        countries=countries,
        continents=[],
        worldwide_remote=False,
        technical_tools=technical_tools,
        requirements_summary=card.get("summary") or "",
        seniority_level=seniority_level,
        posted_str="Unknown",
        url=card.get("url") or "",
        apply_url="",
    )


def _parse_work_and_commitment(line: str) -> tuple[str, str]:
    lowered = line.lower()
    work_type = ""
    for candidate in ("Remote", "Hybrid", "Onsite"):
        if candidate.lower() in lowered:
            work_type = candidate
            break
    commitment = ""
    for candidate in (
        "Full Time",
        "Part Time",
        "Contract",
        "Internship",
        "Temporary",
        "Seasonal",
        "Volunteer",
    ):
        if candidate.lower() in lowered:
            commitment = candidate
            break
    return work_type, commitment


def _looks_like_title_line(line: str) -> bool:
    if line in {"Save", "Mark Applied", "Hide", "Job Posting", "View all"}:
        return False
    if line.startswith(("Image:", "Job Posting", "View all")):
        return False
    if _looks_like_work_line(line) or _looks_like_location_line(line):
        return False
    if "HiringCafe" in line or line.endswith("jobs") or line == "Browse Jobs":
        return False
    return len(line) >= 4 and any(char.isalpha() for char in line)


def _looks_like_location_line(line: str) -> bool:
    lowered = line.lower()
    location_tokens = (
        "united states",
        "germany",
        "poland",
        "europe",
        "remote",
        "hybrid",
        "onsite",
        "location",
        "city",
    )
    return any(token in lowered for token in location_tokens) or "," in line


def _looks_like_work_line(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in ("remote", "hybrid", "onsite", "full time", "part time", "contract"))


def _looks_like_senior_line(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in ("senior", "lead", "principal", "staff", "manager", "director", "vp", "head", "chief"))


def _looks_like_summary_line(line: str) -> bool:
    if _looks_like_meta_line(line):
        return False
    return len(line) > 40 or ";" in line or line.endswith(".")


def _looks_like_tools_line(line: str) -> bool:
    return "," in line and len(line) < 160 and not _looks_like_meta_line(line)


def _looks_like_meta_line(line: str) -> bool:
    lowered = line.lower()
    return lowered in {"save", "mark applied", "hide", "job posting", "view all"} or lowered.startswith("image:")


def _split_tools(line: str) -> list[str]:
    return [tool.strip() for tool in line.split(",") if tool.strip()]
