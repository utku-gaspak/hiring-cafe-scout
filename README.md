# hiring.cafe Job Scraper

Scrapes [hiring.cafe](https://hiring.cafe) for junior/entry-level full-time jobs using a preset-driven CLI. The current built-in preset focuses on software roles in Germany or remote Europe matching `.NET`, `C#`, `ASP.NET`, `TypeScript`, or `React`. Results are saved to `jobs.md` and `jobs.json`, sorted by posting date (newest first).

## Setup

**Requirements:** Python 3.12+, [uv](https://github.com/astral-sh/uv)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt
uv run python -m playwright install chromium
```

## Usage

```bash
uv run scraper.py
```

If run in a normal terminal, the app starts with a preset-first interactive flow:

1. choose the built-in preset, a saved preset, or a new search
2. optionally edit the chosen config
3. build search terms from manual keywords and/or payload-derived skills
3. review and start scraping

Multi-select steps use:

- arrow keys to move
- `Enter` to toggle
- a `Next` row at the bottom to continue

To skip the wizard and run with defaults:

```bash
uv run scraper.py --no-interactive
```

To list presets:

```bash
uv run scraper.py --list-presets
```

To run a specific preset directly:

```bash
uv run scraper.py --preset software-germany-junior --no-interactive
```

To run non-interactively with flags:

```bash
uv run scraper.py \
  --no-interactive \
  --keywords ".NET,React" \
  --workplace-types "Remote,Hybrid" \
  --countries "DE,NL" \
  --cities "Berlin,Hamburg" \
  --seniority-terms "junior,associate,mid" \
  --commitments "Full Time" \
  --markdown-output jobs.md \
  --json-output jobs.json
```

To save and reuse a JSON config file:

```bash
uv run scraper.py --no-interactive --keywords "Python,React" --save-config search.json --save-config-only
uv run scraper.py --config search.json --no-interactive
```

Saved presets are separate from `--config` files. Presets live in `presets/*.json` and are available from startup selection or with `--preset <slug>`.

Output is written to `jobs.md` and `jobs.json` in the same directory unless you override those paths.

## How it works

1. Builds a `?searchState=` query from the resolved config to apply fixed software/IT/engineering categories plus selected seniority buckets server-side.
2. Extracts job data from the page's `__NEXT_DATA__` JSON block (no separate API calls needed).
3. Aggregates payload-derived `technical_tools` across visible results so the interactive wizard can offer live skill selection.
4. Applies keyword, seniority, commitment, and location filters client-side on each page's results.
4. Skips any job already recorded in `seen_ids.txt` so re-runs only surface new postings.
5. Saves new matches to `jobs.md` and `jobs.json`, then appends their IDs to `seen_ids.txt`.

## Deduplication

Each job on hiring.cafe has a stable unique ID (e.g. `grnhse___company___12345`). After every run, the IDs of all matched jobs are appended to `seen_ids.txt`. On the next run those jobs are skipped entirely, so `jobs.md` always contains only **new** postings you haven't seen before.

To reset and re-scrape everything from scratch:

```bash
rm seen_ids.txt
```

## Configuration

You can configure the scraper in three ways:

1. Built-in or saved preset
2. Interactive wizard edits
3. Non-interactive CLI flags
4. JSON config file via `--config`

### Presets

The current default behavior is now a built-in preset:

- `software-germany-junior`

Saved presets can be placed in:

```text
presets/*.json
```

Example saved preset:

```json
{
  "slug": "frontend-berlin",
  "name": "Frontend Berlin",
  "description": "React and TypeScript roles in Berlin",
  "config": {
    "keywords": ["React", "TypeScript"],
    "cities": ["Berlin"]
  }
}
```

The effective config shape is:

| Variable | Default | Description |
|---|---|---|
| `keywords` | `.NET, C#, ASP.NET, TypeScript, React` | Terms matched in job title, tools, and summary |
| `departments` | `Software Development, Information Technology, Engineering` | Fixed internal software-job scope used server-side |
| `workplace_types` | `Remote, Hybrid, Onsite` | Allowed workplace modes |
| `allowed_countries` | `DE` | Allowed onsite/hybrid countries |
| `remote_scopes` | `Europe, Worldwide` | Allowed remote reach |
| `seniority_terms` | `entry, junior, associate, intern, graduate` | Selected seniority labels; can also include `mid`, `senior`, `lead`, `principal`, `staff`, `manager` |
| `include_unspecified_seniority` | `true` | Keeps jobs with blank seniority |
| `commitments` | `Full Time` | Allowed commitment values |
| `markdown_output` | `jobs.md` | Markdown output file path |
| `json_output` | `jobs.json` | Normalized JSON output file path |
| `seen_ids_file` | `seen_ids.txt` | Tracks seen job IDs across runs |
| `include_seen` | `false` | If true, do not skip previously seen jobs |
| `max_pages` | `500` | Safety ceiling on pages scraped; `null` means unlimited |
| `cities` | `[]` | City filter for onsite/hybrid roles |
| `radius_km` | `null` | Optional radius filter |
| `radius_city` | `""` | Center city for radius filtering |

## Location filtering

By default the scraper keeps **all jobs in allowed countries** for onsite/hybrid roles plus **remote jobs open to the selected remote scopes**. You can narrow this down with city names or a radius.

Country options in the interactive wizard are discovered from the live payload. If the payload only exposes ISO codes, the CLI normalizes common European codes back to readable country names like `Germany` and `Netherlands`.

### Filter by cities

For the interactive wizard, Germany has a stable built-in city list. If your selected countries include Germany, you can use `Select Germany cities` or a radius around one of the built-in Germany cities. For everything else, use manual city names with the wizard or `--cities`.

Partial matches work — `"Munich"` matches `"Munich, Bavaria, DE"`.

```bash
uv run scraper.py --no-interactive --cities "Berlin,Munich,Hamburg"
```

Remote jobs are still filtered separately by `remote_scopes`.

### Filter by radius

Use the interactive wizard or `--radius-city` plus `--radius-km` to keep only jobs within a given distance. `radius_city` must be one of the built-in cities in `CITY_COORDS`.

```bash
uv run scraper.py --no-interactive --radius-city Berlin --radius-km 50
```

This uses the exact lat/lon from each job's geolocation data and a haversine distance calculation. Remote jobs are always included regardless of radius.

### Built-in radius cities

The current built-in radius city set is:

- Berlin
- Munich
- Hamburg
- Frankfurt
- Cologne
- Stuttgart
- Düsseldorf
- Leipzig
- Dortmund
- Dresden
- Hannover
- Nuremberg
- Bremen

## Output formats

```
1. Company — Title | Location | WorkType · Commitment | Date | hiring.cafe URL | Apply: <direct link>
```

The JSON export uses a normalized schema that is intended to be stable enough for later database ingestion:

```json
{
  "scraped_at": "2026-05-19T12:00:00+00:00",
  "filters": {
    "keywords": [".NET", "React"],
    "cities": ["Berlin"],
    "radius_km": null,
    "radius_city": "",
    "max_pages": 500
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

## Interactive search terms

The first interactive step combines manual keywords with payload-derived skills:

- `Browse and select skills` opens a filtered list built from aggregated `ssrHits[*].v5_processed_job_data.technical_tools`
- skills are deduped across the visible result set and ranked by frequency
- selected skills move to the top of the list under `Next`
- you can also add manual keywords if the payload-derived skills are incomplete

The wizard requires at least one selected skill or manual keyword before continuing.

## Available payload fields

Everything below is extracted from `__NEXT_DATA__` on each page — no extra requests needed. Fields marked ✓ are already used by the scraper.

## Payload structure for a future CLI

The scraper does not call a separate JSON API. It loads a normal hiring.cafe results page and reads the embedded Next.js payload from:

```text
document.getElementById("__NEXT_DATA__").textContent
```

After parsing that JSON, the useful search data lives under:

```text
props.pageProps
```

Key top-level fields inside `pageProps`:

| Field | Path | Purpose |
|---|---|---|
| Search results | `props.pageProps.ssrHits` | Array of job objects for the current page |
| Total result count | `props.pageProps.ssrTotalCount` | Total number of server-filtered results |
| Last-page flag | `props.pageProps.ssrIsLastPage` | Stops pagination |

Each item in `ssrHits` is a job payload. The current scraper combines that payload with the page's job anchors to build the final result row.

## CLI filter mapping

If you turn this into a CLI, these are the fields that matter most. The useful design principle is: expose user-friendly options, but document the exact payload fields each option depends on.

| CLI option idea | Payload fields | Notes |
|---|---|---|
| `--keywords` | `v5_processed_job_data.core_job_title`, `v5_processed_job_data.technical_tools`, `v5_processed_job_data.requirements_summary`, fallback `job_information.title` | Current scraper matches against title, tools, and summary |
| `--departments` | Server-side `searchState.departments` | Limits the hiring.cafe result universe before client-side filtering |
| `--level` | `v5_processed_job_data.seniority_level` | Good candidates: `entry`, `junior`, `mid`, `senior`, `unspecified` |
| `--full-time-only` | `v5_processed_job_data.commitment` | Current logic accepts anything containing `"full"` |
| `--workplace-type` | `v5_processed_job_data.workplace_type` | Expected values are typically `Remote`, `Hybrid`, `Onsite` |
| `--country DE` | `v5_processed_job_data.workplace_countries` | Array of ISO country codes |
| `--cities Berlin,Hamburg` | `v5_processed_job_data.workplace_cities` | String matching is currently partial and case-insensitive |
| `--radius 50 --radius-city Berlin` | `_geoloc` | Uses job lat/lon data; independent of display text |
| `--remote-europe-only` | `v5_processed_job_data.workplace_type`, `v5_processed_job_data.workplace_continents`, `v5_processed_job_data.boundless_workplace_continents`, `v5_processed_job_data.is_workplace_worldwide_ok` | Current scraper keeps remote jobs open to Europe or worldwide |
| `--posted-after YYYY-MM-DD` | `v5_processed_job_data.estimated_publish_date_millis` | Best field for date comparisons |
| `--salary-disclosed` | `v5_processed_job_data.is_compensation_transparent` | Simple boolean filter |
| `--visa-sponsorship` | `v5_processed_job_data.visa_sponsorship` | Simple boolean filter |

## Normalization rules

Before exposing filters in a CLI, normalize the payload values first. The current scraper already relies on a few implicit normalizations:

| Field | Raw shape | Recommended normalization |
|---|---|---|
| `objectID` / `id` | String, one may be missing | Use `objectID` first, then fallback to `id` |
| `job_information.title` | String | Keep as raw source title |
| `v5_processed_job_data.core_job_title` | String or missing | Prefer over raw title for matching and display |
| `v5_processed_job_data.technical_tools` | Array or missing | Normalize to `list[str]` |
| `v5_processed_job_data.requirements_summary` | String or missing | Normalize missing to empty string |
| `v5_processed_job_data.seniority_level` | String, sometimes blank | Lowercase and trim; blank should be treated as `unspecified` |
| `v5_processed_job_data.commitment` | Usually array, but may vary | Normalize to `list[str]` before filtering |
| `v5_processed_job_data.workplace_type` | String | Lowercase for comparisons, preserve original for display |
| `v5_processed_job_data.workplace_cities` | Array of strings | Normalize to `list[str]`; current matching is substring-based |
| `v5_processed_job_data.workplace_countries` | Array of ISO codes | Normalize to uppercase strings |
| `_geoloc` | Array of `{lat, lon}` objects | Validate coordinates before radius checks |
| `v5_processed_job_data.estimated_publish_date_millis` | Integer Unix ms or missing | Convert once to `datetime` for sorting/filtering |

## Suggested CLI-safe filter model

A practical CLI should expose normalized filters, not raw payload trivia. A reasonable first version would be:

```text
keywords
level
commitment
workplace-type
country
cities
radius-km + radius-city
remote-scope
posted-after
salary-disclosed
visa-sponsorship
```

That gives you enough flexibility to reuse the same payload parsing logic while keeping the CLI stable even if some raw fields are occasionally missing.

### Job

| Field | Path in payload | Notes |
|---|---|---|
| Unique ID ✓ | `objectID` | e.g. `grnhse___company___12345` — stable for the life of the posting |
| Job board source | `source` | `grnhse`, `personio`, `factorial`, `icims2`, … |
| Direct apply link ✓ | `apply_url` | Links straight to Greenhouse / Personio / etc. |
| Raw title | `job_information.title` | Original title including gender notation `(m/w/d)` |
| Normalised title ✓ | `v5_processed_job_data.core_job_title` | Cleaned-up title |
| Requirements summary ✓ | `v5_processed_job_data.requirements_summary` | One-sentence AI summary of the requirements |
| Tech stack ✓ | `v5_processed_job_data.technical_tools` | Array — e.g. `["TypeScript", "React", "AWS"]` |
| Role activities | `v5_processed_job_data.role_activities` | Array of key responsibilities — e.g. `["design system", "write tests"]` |
| Job category | `v5_processed_job_data.job_category` | e.g. `"Information Technology"`, `"Software Development"` |
| Role type | `v5_processed_job_data.role_type` | `"Individual Contributor"` or `"Manager"` |
| Seniority ✓ | `v5_processed_job_data.seniority_level` | `"Entry Level"`, `"Mid Level"`, `"Senior Level"` |
| Min. years experience | `v5_processed_job_data.min_industry_and_role_yoe` | Integer; `null` if not mentioned |
| Commitment ✓ | `v5_processed_job_data.commitment` | Array — e.g. `["Full Time"]` |
| Work type ✓ | `v5_processed_job_data.workplace_type` | `"Remote"`, `"Hybrid"`, `"Onsite"` |
| Location (formatted) ✓ | `v5_processed_job_data.formatted_workplace_location` | Human-readable string |
| Cities ✓ | `v5_processed_job_data.workplace_cities` | Array — e.g. `["Berlin, Berlin, DE"]` |
| Countries ✓ | `v5_processed_job_data.workplace_countries` | Array of ISO codes — e.g. `["DE"]` |
| Geolocation ✓ | `_geoloc` | Array of `{lat, lon}` — one per city, used for radius filtering |
| Salary (yearly) | `v5_processed_job_data.yearly_min_compensation` / `yearly_max_compensation` | `null` if not disclosed |
| Salary currency | `v5_processed_job_data.listed_compensation_currency` | e.g. `"EUR"`, `"USD"` |
| Salary disclosed | `v5_processed_job_data.is_compensation_transparent` | Boolean |
| Language requirements | `v5_processed_job_data.language_requirements` | Array — e.g. `["German", "English"]` |
| Visa sponsorship | `v5_processed_job_data.visa_sponsorship` | Boolean |
| Relocation assistance | `v5_processed_job_data.relocation_assistance` | Boolean |
| 4-day work week | `v5_processed_job_data.four_day_work_week` | Boolean |
| Generous PTO | `v5_processed_job_data.generous_paid_time_off` | Boolean |
| Parental leave | `v5_processed_job_data.generous_parental_leave` | Boolean |
| Posted date ✓ | `v5_processed_job_data.estimated_publish_date_millis` | Unix ms timestamp |

### Company

| Field | Path in payload | Notes |
|---|---|---|
| Name ✓ | `enriched_company_data.name` | |
| Website | `enriched_company_data.homepage_uri` | Domain only, e.g. `"soundcloud.com"` |
| HQ country | `enriched_company_data.hq_country` | ISO code |
| Industries | `enriched_company_data.industries` | Array — e.g. `["Music", "Software"]` |
| Employee count | `enriched_company_data.nb_employees` | Integer |
| Founded | `enriched_company_data.year_founded` | Integer |
| Type | `enriched_company_data.organization_type` | `"Private"`, `"Public"` |
| Last funding type | `enriched_company_data.latest_funding_type` | e.g. `"Series B"`, `"Corporate Round"` |
| Last funding year | `enriched_company_data.latest_funding_year` | Integer |
| Last funding amount | `enriched_company_data.latest_funding_amount` | Integer (USD) |
