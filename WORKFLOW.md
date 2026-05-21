# Workflow

```text
User
  |
  v
abc.com frontend
  |
  | POST /api/scrape { url, include_seen }
  v
abc.com backend
  |
  | creates job row
  | creates run dir + profile dir
  | starts worker
  v
scraper worker
  |
  | runs:
  | uv run cafe-scout \
  |   --url "<hiring.cafe url>" \
  |   --json-output <run>/jobs.json \
  |   --markdown-output <run>/jobs.md \
  |   --progress-output <run>/progress.json \
  |   --browser-profile-dir <profile>
  v
HiringCafe browser session
  |
  | if normal page -> scrape listings
  | if Cloudflare -> pause for manual verification
  v
progress.json updates
  |
  | backend polls/reads progress.json
  v
frontend status page
  |
  | shows progress / verification / done / failed
  v
final artifacts
  |
  | GET /api/scrape/{job_id}/jobs.json
  | GET /api/scrape/{job_id}/jobs.md
  v
user downloads results
```

```text
Cloudflare branch

scraper -> browser opens -> challenge appears
                           |
                           v
                    user opens verification page
                           |
                           v
                   user clears challenge manually
                           |
                           v
                    backend resumes same job
                           |
                           v
                     scraper continues scraping
```

```text
Data flow

HiringCafe URL
   -> backend job record
   -> scraper command
   -> browser scrape
   -> jobs.json / jobs.md / progress.json
   -> backend status API
   -> frontend progress UI
```
