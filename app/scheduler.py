from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from .database import SessionLocal
from .services import get_or_create_settings, scrape_and_persist

scheduler = BackgroundScheduler()


def scrape_job() -> None:
    db: Session = SessionLocal()
    try:
        scrape_and_persist(db)
    finally:
        db.close()


def schedule_scraping() -> None:
    db: Session = SessionLocal()
    try:
        settings = get_or_create_settings(db)
        minutes = max(1, settings.scrape_interval_minutes)
    finally:
        db.close()

    if scheduler.get_job("scrape_job"):
        scheduler.remove_job("scrape_job")

    scheduler.add_job(scrape_job, "interval", minutes=minutes, id="scrape_job", replace_existing=True)

    if not scheduler.running:
        scheduler.start()
