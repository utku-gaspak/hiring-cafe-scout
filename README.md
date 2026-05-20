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

## Demo

![CLI demo](assets/demo1.gif)

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
uv run cafe-scout --url "https://hiring.cafe/?searchState=..."
```

When `--url` is set, the pasted HiringCafe link becomes the source of truth and
the scraper parses every job from that search state.

If HiringCafe keeps reloading the Cloudflare challenge, use `--browser-profile-dir` so the scraper keeps a real Chromium profile open while it fetches jobs. The browser requests happen inside that same session, so the API calls inherit the browser state directly.

The storage-state export is still available if you want to inspect or reuse cookies manually:

```bash
uv run cafe-scout --export-session-state browser-session.json
```

That opens a real browser, lets you clear the challenge manually, and saves the browser session for later runs.

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

## Engineering decisions

- Uses HiringCafe's JSON search API when building searches from flags or presets
- Supports a URL pass-through mode that parses the pasted HiringCafe search state directly
- Keeps server-side search broad, then applies local keyword, location, commitment, and seniority filtering unless `--url` is set
- Can reuse a browser-cleared session via a storage-state JSON file when Cloudflare blocks cold requests
- Deduplication via `seen_ids.txt` so daily runs only surface new postings
- Preset system makes repeated searches reproducible without editing source code
