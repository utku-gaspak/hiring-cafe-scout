# hiring-cafe-scout

A CLI tool that searches [hiring.cafe](https://hiring.cafe) for job postings matching your exact tech stack and exports a clean list with direct apply links.

Mainstream job portals like LinkedIn have poor keyword matching for specific terms like `.NET` or `C#`, and applying through third-party platforms reduces visibility compared to applying directly on company websites. hiring-cafe-scout solves both problems: it finds exact matches using hiring.cafe's structured data and exports direct company apply links so you can apply where it counts.

## What it does

- Interactive CLI wizard to build and save reusable search presets
- Filters by keywords, seniority, location, workplace type, and commitment
- Supports radius-based filtering around German cities
- Deduplicates across runs:  only new postings appear each time
- Exports to `jobs.md` and `jobs.json` with direct company apply links

## Demo

![Interactive demo](assets/demo1.gif)

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python -m playwright install chromium
```

## Usage

```bash
uv run cafe-scout
```

The wizard walks you through keyword selection, location, seniority, and workplace filters. Save the config as a preset for daily reuse.

To run non-interactively with a saved preset:

```bash
uv run cafe-scout --preset software-germany-junior --no-interactive
```

To run with custom flags:

```bash
uv run cafe-scout \
  --no-interactive \
  --keywords ".NET,React" \
  --workplace-types "Remote,Hybrid" \
  --countries "DE" \
  --seniority-terms "junior,entry" \
  --commitments "Full Time"
```

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

- Reads `__NEXT_DATA__` from the rendered page instead of scraping the DOM-  more stable and gives access to structured job metadata without a public API
- Server-side department filtering combined with client-side keyword and seniority matching for precise results
- Deduplication via `seen_ids.txt` so daily runs only surface new postings
- Preset system makes repeated searches reproducible without editing source code
