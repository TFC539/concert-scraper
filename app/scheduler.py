from apscheduler.schedulers.background import BackgroundScheduler
import logging
from sqlalchemy.orm import Session

from .database import SessionLocal
from .services import get_or_create_settings, scrape_and_persist

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


def scrape_job() -> None:
    db: Session = SessionLocal()
    logger.info("scrape_job_started")
    try:
        inserted = scrape_and_persist(db)
        logger.info("scrape_job_finished inserted=%s", inserted)
    except Exception:
        logger.exception("scrape_job_failed")
        raise
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
        logger.info("scrape_schedule_replaced")

    scheduler.add_job(scrape_job, "interval", minutes=minutes, id="scrape_job", replace_existing=True)
    logger.info("scrape_schedule_set interval_minutes=%s", minutes)

    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler_started")
