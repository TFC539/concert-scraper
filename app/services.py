from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSettings, Concert, NotificationRule
from .scrapers import scrape_all


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
        (rule.performer_contains, concert.performers or ""),
        (rule.program_contains, concert.program or ""),
        (rule.date_contains, concert.date or ""),
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
        f"Time: {concert.time}\n"
        f"Performers: {concert.performers}\n"
        f"Program: {concert.program}\n"
        f"URL: {concert.source_url}\n"
    )
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def scrape_and_persist(db: Session) -> int:
    settings = get_or_create_settings(db)
    rules = db.scalars(select(NotificationRule)).all()

    inserted = 0
    scraped = scrape_all()
    for item in scraped:
        exists = db.scalar(
            select(Concert).where(
                Concert.source == item.source,
                Concert.external_id == item.external_id,
            )
        )

        if exists:
            continue

        concert = Concert(
            source=item.source,
            source_url=item.source_url,
            external_id=item.external_id,
            name=item.name,
            program=item.program,
            performers=item.performers,
            date=item.date,
            time=item.time,
        )
        db.add(concert)
        db.flush()
        inserted += 1

        if settings.notifications_enabled:
            matching = [rule for rule in rules if should_notify(concert, rule)]
            if matching:
                try:
                    send_email(settings, concert, matching)
                except Exception:
                    pass

    db.commit()
    return inserted
