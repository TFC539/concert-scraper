# Concert Scraper Dashboard

A FastAPI dashboard that periodically scrapes concerts from:
- Elbphilharmonie
- ProArte

It stores concerts in SQLite, provides dashboard filtering, and can send email notifications when user-defined rules match newly imported concerts.

## Features
- Scheduler with configurable interval.
- Scrape-now button.
- Metadata ingestion: concert name, program, performers, date, time, source URL.
- Filter concerts by free-text, source, and date.
- Notification rules on all metadata fields.
- SMTP settings editable in dashboard.

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000

## Notes
- Scraping selectors may need occasional adjustment if source websites change their HTML structure.
- Email notifications are sent only for newly inserted concerts.
