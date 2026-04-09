# Concert Scraper Dashboard

A FastAPI dashboard that periodically scrapes concerts from:
- Elbphilharmonie
- ProArte

It stores concerts in SQLite, provides dashboard filtering, and can send email notifications when user-defined rules match newly imported concerts.

## Features
- Scheduler with configurable interval.
- Multi-page dashboard (overview, scrape control, concert explorer, resolution, notifications).
- Scoped scrape runs (multi-source selection, max per source, max total).
- Dump current filtered concerts as JSON directly from the dashboard.
- Metadata ingestion: concert name, program, performers, hall, date (raw + normalized), time, source URL.
- Filter concerts by free-text, source, and date.
- Notification rules on all metadata fields.
- SMTP settings editable in dashboard.

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY="your-key"
# Optional overrides:
# export OPENROUTER_MODEL="openai/gpt-4.1-mini"
# export OPENROUTER_TIMEOUT_SECONDS="40"
# export OPENROUTER_MAX_RETRIES="2"
uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000

## Logging
- App logs are written to `logs/app.log` and `logs/error.log`.
- Logs are also emitted to the terminal.
- Optional environment variables:
	- `APP_LOG_DIR` (default: `logs`)
	- `APP_LOG_LEVEL` (default: `INFO`)
	- `APP_LOG_MAX_BYTES` (default: `5242880`)
	- `APP_LOG_BACKUP_COUNT` (default: `5`)

## Notes
- Scraping selectors may need occasional adjustment if source websites change their HTML structure.
- Email notifications are sent only for newly inserted concerts.

## Entity Resolution Pipeline

The runtime processes scraped concerts through:

Scraper -> Extraction (OpenRouter) -> Normalization -> Candidate Retrieval -> Matching -> Suggestions -> Resolution -> Database

Implemented behavior:
- Deterministic matching first (aliases, normalized forms, fuzzy scoring).
- Optional LLM-assisted disambiguation for ambiguous matches (assistive only, not a canonical write decision).
- Unresolved queues with manual resolution actions.
- Merge suggestions with merge/reject/do-not-merge review actions.
- Feedback loop updates (alias enrichment + do-not-merge safeguards).
- Triage buckets for non-safe matches (critical/open and medium/deferred).
- Proposal-first writes for uncertain entities (no direct canonical auto-create on low confidence).
- Batch resolution support (apply one decision to similar unresolved entries).
- Contributor authentication with trust levels (merge review restricted to trusted/verified users).
- Role-based access: SMTP/OpenRouter/system configuration is admin-only.
- User-owned notifications: normal accounts can manage their own recipient email, enable/disable alerts, and define personal rules.
- Admin-only operations: scrape triggers and concert deletion endpoints.
- Signed-out dashboard scope: Concert Explorer only.

New API surfaces for review workflows:
- `GET /api/resolution/unresolved`
- `POST /api/resolution/unresolved/{id}`
- `GET /api/resolution/merge-suggestions`
- `POST /api/resolution/merge-suggestions/{id}`

Authentication API surfaces:
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Notification profile API surfaces:
- `GET /api/notifications/profile`
- `PUT /api/notifications/profile`

Manual scrape and export API surfaces:
- `POST /api/scrape-now` (supports `sources`, `max_per_source`, `max_total`)
- `GET /api/scrape/sources`
- `GET /api/concerts/dump`

The dashboard UI includes review panels for unresolved entities and merge suggestions.

If `OPENROUTER_API_KEY` is not set, extraction falls back to a deterministic flat-field parser and records the fallback in extraction audit entries.

## ML Status

The `ml/` directory is deprecated archival tooling and is not used by the FastAPI runtime pipeline in `app/`.
