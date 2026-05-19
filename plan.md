# Project Plan

## Goal

Turn the current single-file scraper into a reliable Python CLI application with:

- an interactive setup flow in the terminal
- reusable filtering logic
- stable normalized job data
- markdown output like today
- JSON output for future database ingestion

The scraper should remain Python-based because the hard part is browser automation and payload extraction from hiring.cafe, not raw CPU speed.

## Product direction

The app should feel like a guided setup wizard rather than a plain script with hardcoded constants.

The intended user flow:

1. Start the CLI.
2. Enter one keyword at a time.
3. Type `0` to finish keyword entry.
4. Move through filter sections step by step.
5. Review the selected configuration.
6. Start the scrape.
7. Save results as markdown, JSON, or both.

This keeps the user experience simple while preserving a clean internal architecture.

## Target architecture

Instead of growing `scraper.py`, split the app into small modules with clear responsibilities.

Suggested package layout:

```text
job_parser/
  __init__.py
  cli.py
  wizard.py
  config.py
  models.py
  scraper.py
  payload.py
  filters.py
  exporters/
    __init__.py
    markdown.py
    json.py
tests/
```

Module responsibilities:

- `cli.py`
  - application entry point
  - decides whether to run interactive mode or flag-based mode later

- `wizard.py`
  - terminal setup flow
  - keyword collection
  - multi-select filters
  - final confirmation screen

- `config.py`
  - stores validated user-selected filters
  - converts wizard answers into a structured config object

- `models.py`
  - normalized internal data models
  - should define a stable `Job` model and a `SearchConfig` model

- `scraper.py`
  - Playwright browser lifecycle
  - page loading
  - pagination

- `payload.py`
  - extraction of `__NEXT_DATA__`
  - raw payload parsing helpers
  - payload-to-model normalization

- `filters.py`
  - keyword, location, seniority, commitment, remote-scope, and radius filtering
  - should work on normalized `Job` objects, not raw payload dictionaries

- `exporters/markdown.py`
  - output format compatible with current `jobs.md`

- `exporters/json.py`
  - normalized JSON output for future DB integration

## Data model

The most important design decision is to define a stable normalized job schema.

Suggested `Job` fields:

```text
id
source
title
raw_title
company
location_display
workplace_type
commitment
cities
countries
continents
worldwide_remote
technical_tools
requirements_summary
seniority_level
min_years_experience
salary_min
salary_max
salary_currency
salary_disclosed
language_requirements
visa_sponsorship
relocation_assistance
posted_at
job_url
apply_url
geolocations
```

Suggested `SearchConfig` fields:

```text
keywords
workplace_types
countries
cities
radius_km
radius_city
seniority_levels
commitments
remote_scope
output_formats
max_pages
include_seen
```

This schema should become the contract between scraping, filtering, exporting, and future database usage.

## Interactive wizard design

The CLI should behave like a guided setup screen.

Recommended flow:

### 1. Keywords

Prompt:

```text
Enter a keyword and press Enter.
Type 0 when finished.
```

Rules:

- ignore empty input
- trim whitespace
- deduplicate case-insensitively
- require at least one keyword before continuing

### 2. Workplace type

Multi-select:

- Remote
- Hybrid
- Onsite

Default:

- all selected

### 3. Country scope

First version can stay simple:

- Germany only
- custom country codes

Since the current scraper is Germany-focused, this can remain narrow at first.

### 4. City filter

User chooses one of:

- no city filter
- select from common cities
- enter custom city names

This should remain independent from remote filtering, since remote jobs may still pass separately.

### 5. Radius filter

User chooses:

- no radius filter
- radius around a city

If radius is enabled:

- ask for radius city
- ask for radius in km

This should take precedence over city-list filtering, matching current behavior.

### 6. Seniority filter

Multi-select:

- Entry Level
- Junior
- Associate
- Intern
- Graduate
- Unspecified

Optional later:

- Mid
- Senior

### 7. Commitment filter

Multi-select:

- Full Time
- Part Time
- Contract

Even if the first implementation still defaults to full-time, the data model should support broader values.

### 8. Remote scope

Multi-select:

- Europe
- Worldwide

### 9. Output format

Multi-select:

- Markdown
- JSON

Default:

- both

### 10. Review screen

Print the final config in a compact summary and ask:

```text
Start scraping with these settings?
```

Options:

- yes
- edit
- cancel

## Recommended libraries

For a polished terminal wizard, prefer one of:

- `questionary`
- `InquirerPy`

Recommendation:

- use `questionary` first

Why:

- simpler for select, checkbox, confirm, and text prompts
- enough polish for a guided CLI
- less work than building prompt UX manually

If dependency minimization becomes more important later, the wizard can be downgraded to `argparse` plus plain `input()` prompts, but that should not be the first choice for UX.

## Output strategy

The app should no longer treat markdown as the primary data model.

Instead:

1. scrape raw payloads
2. normalize to `Job` objects
3. apply filters to normalized objects
4. export the same result set into one or more formats

Output formats:

- Markdown
  - human-readable browsing
  - keep similar structure to current `jobs.md`

- JSON
  - normalized machine-readable export
  - should be stable enough for later DB ingestion

Suggested JSON shape:

```json
{
  "scraped_at": "2026-05-19T12:00:00Z",
  "filters": {
    "keywords": ["python", "react"],
    "cities": ["Berlin"],
    "workplace_types": ["Remote", "Hybrid"]
  },
  "results": [
    {
      "id": "personio___company___123",
      "title": "Software Engineer",
      "company": "Example Co",
      "location_display": "Berlin, Berlin, Germany",
      "workplace_type": "Remote",
      "commitment": "Full Time",
      "cities": ["Berlin, Berlin, DE"],
      "countries": ["DE"],
      "posted_at": "2026-05-19",
      "job_url": "https://hiring.cafe/job/...",
      "apply_url": "https://company.com/apply/..."
    }
  ]
}
```

## Reliability requirements

This project should optimize for reliability over cleverness.

That means:

- isolate all payload access in one place
- normalize missing or inconsistent fields before filtering
- avoid mixing raw payload dicts into output code
- keep browser retry logic explicit
- log failures without crashing the whole run where possible
- use stable defaults when payload fields are missing
- keep filtering deterministic and testable

## Testing plan

Add tests before expanding features too far.

Priority test coverage:

- keyword matching
- seniority normalization and filtering
- commitment normalization
- city matching
- radius filtering
- remote Europe/worldwide logic
- payload normalization for missing fields
- markdown export shape
- JSON export shape

Use fixture payload samples captured from real pages so filtering tests do not depend on live scraping.

## Migration plan

Implement in stages instead of rewriting everything at once.

### Phase 1

- create package structure
- move current logic out of monolithic `scraper.py`
- define `Job` and `SearchConfig`
- preserve current behavior

### Phase 2

- add normalized JSON export
- add test fixtures and unit tests
- make markdown generation consume normalized jobs

### Phase 3

- add interactive wizard
- replace hardcoded constants with wizard-driven config
- add review/confirm screen

### Phase 4

- add optional non-interactive flags
- support config file or saved presets
- prepare JSON export for database sync

## Portfolio value

This direction is stronger than leaving the project as a single script because it demonstrates:

- CLI application design
- modular architecture
- data normalization
- testability
- future-ready integration design

That is much more portfolio-worthy than “a scraper that writes one markdown file”.

## Immediate next step

The next implementation step should be:

1. define `Job` and `SearchConfig`
2. extract payload normalization from the current scraper
3. add JSON export
4. only then build the interactive wizard

That order keeps the UI from being built on unstable internals.
