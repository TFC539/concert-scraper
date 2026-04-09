from __future__ import annotations

import logging
import smtplib
import unicodedata
from email.message import EmailMessage
from datetime import date, datetime
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .entity_pipeline import process_concert_entity_pipeline
from .models import AppSettings, Concert, Event, EventPerformer, EventWork, NotificationRule, UnresolvedEntity
from .scrapers import scrape_all


logger = logging.getLogger(__name__)


MONTH_MAP = {
    "jan": 1,
    "januar": 1,
    "january": 1,
    "feb": 2,
    "februar": 2,
    "february": 2,
    "mar": 3,
    "maerz": 3,
    "marz": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "juni": 6,
    "june": 6,
    "jul": 7,
    "juli": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "okt": 10,
    "october": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "dez": 12,
    "december": 12,
    "dezember": 12,
}


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _parse_concert_date(date_text: str) -> date | None:
    if not date_text:
        return None

    normalized = _normalize_text(date_text)
    normalized = normalized.replace(",", " ")

    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            pass

    parts = [part for part in re.split(r"[\s.]+", normalized) if part]
    if len(parts) >= 3:
        # Formats like: Tue 31 Mar 2026 / Dienstag 31 Maerz 2026
        candidates = parts[-3:]
        day_str, month_str, year_str = candidates
        if day_str.isdigit() and year_str.isdigit():
            month_number = MONTH_MAP.get(month_str[:3], MONTH_MAP.get(month_str))
            if month_number:
                try:
                    return date(int(year_str), month_number, int(day_str))
                except ValueError:
                    return None

    return None


def _normalize_date_text(date_text: str) -> str:
    parsed = _parse_concert_date(date_text)
    return parsed.isoformat() if parsed else ""


HALL_HINTS = (
    "saal",
    "halle",
    "philharmonie",
    "kirche",
    "arena",
    "theater",
)


def _looks_like_hall_text(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(hint in normalized for hint in HALL_HINTS)


def _is_upcoming(date_text: str, reference_date: date) -> bool:
    parsed = _parse_concert_date(date_text)
    if parsed is None:
        # Unknown format should not block initial population.
        return True
    return parsed >= reference_date


def backfill_concert_metadata(db: Session) -> int:
    concerts = db.scalars(select(Concert)).all()
    changed = 0

    for concert in concerts:
        updated = False

        normalized_date = _normalize_date_text(concert.date or "")
        if normalized_date and (concert.date_normalized or "") != normalized_date:
            concert.date_normalized = normalized_date
            updated = True

        if (concert.source or "").strip().lower() == "proarte":
            hall = (concert.hall or "").strip()
            performers = (concert.performers or "").strip()
            if not hall and performers and _looks_like_hall_text(performers):
                concert.hall = performers
                concert.performers = ""
                updated = True

        if updated:
            changed += 1

    if changed:
        db.commit()
        logger.info("backfill_metadata_updated changed=%s", changed)
    else:
        logger.info("backfill_metadata_no_changes")

    return changed


def get_or_create_settings(db: Session) -> AppSettings:
    settings = db.scalar(select(AppSettings).limit(1))
    if settings:
        return settings

    settings = AppSettings()
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def should_notify(concert: Concert, rule: NotificationRule) -> bool:
    if not rule.enabled:
        return False

    checks = [
        (rule.name_contains, concert.name),
        (
            rule.performer_contains,
            " | ".join(part for part in [concert.performers or "", concert.name or ""] if part),
        ),
        (rule.program_contains, concert.program or ""),
        (rule.date_contains, " ".join(part for part in [concert.date or "", concert.date_normalized or ""] if part)),
        (rule.time_contains, concert.time or ""),
    ]

    for needle, haystack in checks:
        if needle and needle.lower() not in haystack.lower():
            return False

    return True


def send_email(settings: AppSettings, concert: Concert, matching_rules: list[NotificationRule]) -> None:
    if not (settings.sender_email and settings.recipient_email and settings.smtp_host):
        return

    message = EmailMessage()
    message["Subject"] = f"Concert Alert: {concert.name}"
    message["From"] = settings.sender_email
    message["To"] = settings.recipient_email

    rule_names = ", ".join(str(rule.id) for rule in matching_rules)
    body = (
        f"A concert matched your rules ({rule_names}).\n\n"
        f"Source: {concert.source}\n"
        f"Name: {concert.name}\n"
        f"Date: {concert.date}\n"
        f"Normalized date: {concert.date_normalized}\n"
        f"Time: {concert.time}\n"
        f"Performers: {concert.performers}\n"
        f"Hall: {concert.hall}\n"
        f"Program: {concert.program}\n"
        f"URL: {concert.source_url}\n"
    )
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def scrape_and_persist(
    db: Session,
    sources: list[str] | None = None,
    max_per_source: int | None = None,
    max_total: int | None = None,
) -> int:
    settings = get_or_create_settings(db)
    rules = db.scalars(select(NotificationRule)).all()
    is_initial_import = db.scalar(select(Concert.id).limit(1)) is None
    today = datetime.utcnow().date()

    inserted = 0
    scraped = scrape_all(
        sources=sources,
        max_per_source=max_per_source,
        max_total=max_total,
    )
    logger.info(
        "scrape_persist_started scraped_count=%s initial_import=%s sources=%s max_per_source=%s max_total=%s",
        len(scraped),
        is_initial_import,
        sources or ["all"],
        max_per_source,
        max_total,
    )
    for item in scraped:
        normalized_date = _normalize_date_text(item.date)

        if is_initial_import and not _is_upcoming(item.date, today):
            continue

        exists = db.scalar(
            select(Concert).where(
                Concert.source == item.source,
                Concert.external_id == item.external_id,
            )
        )

        if exists:
            updated = False

            if normalized_date and (exists.date_normalized or "") != normalized_date:
                exists.date_normalized = normalized_date
                updated = True

            if item.hall and (exists.hall or "") != item.hall:
                exists.hall = item.hall
                updated = True

            if item.performers and (exists.performers or "") != item.performers:
                exists.performers = item.performers
                updated = True

            if item.program and (exists.program or "") != item.program:
                exists.program = item.program
                updated = True

            existing_event_id = db.scalar(select(Event.id).where(Event.concert_id == exists.id).limit(1))
            needs_entity_processing = existing_event_id is None

            needs_normalized_backfill = False
            if existing_event_id is not None:
                has_open_unresolved = (
                    db.scalar(
                        select(UnresolvedEntity.id)
                        .where(UnresolvedEntity.event_id == existing_event_id)
                        .where(UnresolvedEntity.status == "open")
                        .limit(1)
                    )
                    is not None
                )
                has_performer_links = (
                    db.scalar(select(EventPerformer.id).where(EventPerformer.event_id == existing_event_id).limit(1))
                    is not None
                )
                has_work_links = (
                    db.scalar(select(EventWork.id).where(EventWork.event_id == existing_event_id).limit(1)) is not None
                )
                needs_normalized_backfill = has_open_unresolved and not has_performer_links and not has_work_links

            if updated or needs_entity_processing or needs_normalized_backfill:
                db.add(exists)
                db.flush()
                try:
                    process_concert_entity_pipeline(db, exists)
                except Exception:
                    logger.exception("Entity pipeline failed for updated concert id=%s", exists.id)
            continue

        concert = Concert(
            source=item.source,
            source_url=item.source_url,
            external_id=item.external_id,
            name=item.name,
            program=item.program,
            performers=item.performers,
            hall=item.hall,
            date=item.date,
            date_normalized=normalized_date,
            time=item.time,
        )
        db.add(concert)
        db.flush()
        inserted += 1

        try:
            process_concert_entity_pipeline(db, concert)
        except Exception:
            logger.exception("Entity pipeline failed for new concert id=%s", concert.id)

        if settings.notifications_enabled:
            matching = [rule for rule in rules if should_notify(concert, rule)]
            if matching:
                try:
                    send_email(settings, concert, matching)
                except Exception:
                    logger.exception("notification_email_failed concert_id=%s", concert.id)

    db.commit()
    logger.info("scrape_persist_finished inserted=%s", inserted)
    return inserted
