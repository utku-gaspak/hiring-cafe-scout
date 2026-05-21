# hiring-cafe-scout

A CLI tool that searches [hiring.cafe](https://hiring.cafe) for job postings matching your exact tech stack and exports a clean list with direct apply links.

Mainstream job portals like LinkedIn have poor keyword matching for specific terms like `.NET` or `C#`, and applying through third-party platforms reduces visibility compared to applying directly on company websites. hiring-cafe-scout solves both problems: it finds exact matches using hiring.cafe's structured data and exports direct company apply links so you can apply where it counts.
The default run applies HiringCafe's entry-level seniority filter and lets you
override the keyword at runtime.

## What it does

- Non-interactive CLI for preset-based or flag-based job searches
- Filters by keywords, seniority, location, workplace type, and commitment
- Supports radius-based filtering around German cities
- Deduplicates across runs:  only new postings appear each time
- Exports to `jobs.md` and `jobs.json` with direct company apply links
- Can emit `progress.json` for web-app/backend progress displays

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

The main scrape path uses Pydoll browser-context requests. If you want the optional
`--export-session-state` helper, also install Playwright Chromium once:

```bash
uv run playwright install chromium
```

## Usage

Run the default preset:

```bash
uv run cafe-scout
```

To search for a different entry-level keyword:

```bash
uv run cafe-scout --keywords "C#"
```

To run with a saved preset:

```bash
uv run cafe-scout --preset software-germany-junior
```

To run with custom flags:

```bash
uv run cafe-scout \
  --keywords ".NET,React" \
  --workplace-types "Remote,Hybrid" \
  --countries "DE" \
  --seniority-terms "junior,entry" \
  --commitments "Full Time" \
  --browser-profile-dir browser-profile
```

To run a pasted HiringCafe search URL as-is:

```bash
uv run cafe-scout \
  --url "https://hiring.cafe/?searchState=..." \
  --json-output runs/manual/jobs.json \
  --markdown-output runs/manual/jobs.md \
  --browser-profile-dir browser-profile
```

When `--url` is set, the pasted HiringCafe link becomes the source of truth and
the scraper parses every job from that search state.

For web-app/backend integrations, also write machine-readable progress:

```bash
uv run cafe-scout \
  --url "$HIRING_CAFE_URL" \
  --json-output "$RUN_DIR/jobs.json" \
  --markdown-output "$RUN_DIR/jobs.md" \
  --progress-output "$RUN_DIR/progress.json" \
  --browser-profile-dir "$PROFILE_DIR"
```

`progress.json` is updated during browser scraping:

```json
{
  "status": "running",
  "pages_scraped": 2,
  "visible_jobs_scraped": 60,
  "matched_jobs": 12,
  "estimated_total_jobs": 230,
  "total_is_estimate": true,
  "progress_percent": 26,
  "current_page_listings": 30,
  "current_page_matched": 6,
  "skipped_seen": 4,
  "message": "Scraped page 2"
}
```

HiringCafe's visible total can be stale or inflated, so treat
`estimated_total_jobs` and `progress_percent` as UI feedback only. Final counts
should come from `jobs.json`.

If HiringCafe shows a Cloudflare challenge, use `--browser-profile-dir` so the scraper keeps a real Chromium profile. Clear the challenge manually in the browser window, then press Enter in the CLI. Do not paste cookies; the profile directory is the session.

The storage-state export is still available for local inspection:

```bash
uv run cafe-scout --export-session-state browser-session.json
```

That opens a real browser, lets you clear the challenge manually, and saves the browser session state.

To use the persistent browser profile flow instead:

```bash
uv run cafe-scout --browser-profile-dir browser-profile
```

The browser stays open while scraping, so Cloudflare state survives within the same session.

To list or delete saved presets:

```bash
uv run cafe-scout --list-presets
uv run cafe-scout --delete-preset <slug>
```

To reset deduplication and re-scrape everything:

```bash
rm seen_ids.txt
```

## Output

Each result in `jobs.md`:

```
1. Company — Title | Location | WorkType | Date | hiring.cafe URL | Apply: <direct link>
```

`jobs.json` exports the same data in a normalized schema for further processing.

Output parent directories are created automatically, so paths like
`runs/manual/jobs.json` work even when `runs/manual` does not exist yet.

## Engineering decisions

- Uses browser-context scraping when Cloudflare blocks direct requests
- Supports a URL pass-through mode that opens the pasted HiringCafe search URL directly
- Keeps server-side search broad, then applies local keyword, location, commitment, and seniority filtering unless `--url` is set
- Can reuse a browser-cleared session via a persistent Chromium profile directory
- Writes optional progress JSON for backend/frontend polling
- Deduplication via `seen_ids.txt` so daily runs only surface new postings
- Preset system makes repeated searches reproducible without editing source code
