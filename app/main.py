import re
import unicodedata

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, ensure_schema, get_db
from .models import Concert, NotificationRule
from .scheduler import schedule_scraping, scrape_job
from .schemas import RuleCreate, SettingsUpdate
from .services import backfill_concert_metadata, get_or_create_settings

Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Concert Dashboard")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _is_maybe_concert(concert: Concert) -> bool:
    name_normalized = _normalize_text(concert.name)
    if not name_normalized:
        return False

    if name_normalized.startswith("fur das konzert mit "):
        return True

    indicators = [
        "jetzt platze auf dem podium buchbar",
        "jetzt plaetze auf dem podium buchbar",
        "sind jetzt",
        "buchbar",
    ]
    score = sum(1 for indicator in indicators if indicator in name_normalized)

    has_sentence_shape = len(name_normalized) > 90 and name_normalized.endswith(".")
    source_is_proarte = (concert.source or "").strip().lower() == "proarte"

    return source_is_proarte and (score >= 2 or (score >= 1 and has_sentence_shape))


@app.on_event("startup")
def startup() -> None:
    db = SessionLocal()
    try:
        backfill_concert_metadata(db)
    finally:
        db.close()

    schedule_scraping()


def _concert_to_dict(concert: Concert) -> dict:
    return {
        "id": concert.id,
        "source": concert.source,
        "source_url": concert.source_url,
        "name": concert.name,
        "program": concert.program or "",
        "performers": concert.performers or "",
        "hall": concert.hall or "",
        "date": concert.date or "",
        "date_normalized": concert.date_normalized or "",
        "time": concert.time or "",
        "fetched_at": concert.fetched_at.isoformat() if concert.fetched_at else None,
        "maybe_concert": _is_maybe_concert(concert),
    }


def _rule_to_dict(rule: NotificationRule) -> dict:
    return {
        "id": rule.id,
        "name_contains": rule.name_contains or "",
        "performer_contains": rule.performer_contains or "",
        "program_contains": rule.program_contains or "",
        "date_contains": rule.date_contains or "",
        "time_contains": rule.time_contains or "",
        "enabled": bool(rule.enabled),
    }


def _settings_to_dict(settings) -> dict:
    return {
        "scrape_interval_minutes": settings.scrape_interval_minutes,
        "smtp_host": settings.smtp_host or "",
        "smtp_port": settings.smtp_port,
        "smtp_username": settings.smtp_username or "",
        "smtp_password": settings.smtp_password or "",
        "sender_email": settings.sender_email or "",
        "recipient_email": settings.recipient_email or "",
        "notifications_enabled": bool(settings.notifications_enabled),
    }


def _get_dashboard_payload(
    db: Session,
    q: str = "",
    source: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
) -> dict:
    settings = get_or_create_settings(db)

    query = select(Concert).order_by(Concert.fetched_at.desc())
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Concert.name.like(pattern),
                Concert.program.like(pattern),
                Concert.performers.like(pattern),
                Concert.hall.like(pattern),
            )
        )
    if source:
        query = query.where(Concert.source == source)
    if date_filter:
        pattern = f"%{date_filter}%"
        query = query.where(or_(Concert.date.like(pattern), Concert.date_normalized.like(pattern)))

    concerts = db.scalars(query.limit(2500)).all()
    concerts_payload = [_concert_to_dict(concert) for concert in concerts]

    if include_maybe:
        visible_concerts = concerts_payload
        maybe_hidden_count = 0
    else:
        visible_concerts = [concert for concert in concerts_payload if not concert["maybe_concert"]]
        maybe_hidden_count = len(concerts_payload) - len(visible_concerts)

    visible_concerts = visible_concerts[:500]
    rules = db.scalars(select(NotificationRule).order_by(NotificationRule.id.desc())).all()

    sources = sorted({concert["source"] for concert in visible_concerts if concert["source"]})

    return {
        "concerts": visible_concerts,
        "rules": [_rule_to_dict(rule) for rule in rules],
        "settings": _settings_to_dict(settings),
        "filters": {
            "q": q,
            "source": source,
            "date_filter": date_filter,
            "include_maybe": include_maybe,
        },
        "maybe_hidden_count": maybe_hidden_count,
        "sources": sources,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    q: str = "",
    source: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request},
    )


@app.get("/api/dashboard")
def api_dashboard(
    q: str = "",
    source: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    db: Session = Depends(get_db),
):
    return _get_dashboard_payload(
        db,
        q=q,
        source=source,
        date_filter=date_filter,
        include_maybe=include_maybe,
    )


@app.post("/settings")
def update_settings(
    scrape_interval_minutes: int = Form(...),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    sender_email: str = Form(""),
    recipient_email: str = Form(""),
    notifications_enabled: str | None = Form(None),
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db)
    settings.scrape_interval_minutes = max(1, scrape_interval_minutes)
    settings.smtp_host = smtp_host.strip()
    settings.smtp_port = smtp_port
    settings.smtp_username = smtp_username.strip()
    settings.smtp_password = smtp_password
    settings.sender_email = sender_email.strip()
    settings.recipient_email = recipient_email.strip()
    settings.notifications_enabled = notifications_enabled == "on"
    db.commit()

    schedule_scraping()
    return RedirectResponse(url="/", status_code=303)


@app.put("/api/settings")
def api_update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    settings.scrape_interval_minutes = max(1, payload.scrape_interval_minutes)
    settings.smtp_host = payload.smtp_host.strip()
    settings.smtp_port = payload.smtp_port
    settings.smtp_username = payload.smtp_username.strip()
    settings.smtp_password = payload.smtp_password
    settings.sender_email = str(payload.sender_email or "").strip()
    settings.recipient_email = str(payload.recipient_email or "").strip()
    settings.notifications_enabled = payload.notifications_enabled
    db.commit()

    schedule_scraping()
    return {"ok": True, "settings": _settings_to_dict(settings)}


@app.post("/rules")
def create_rule(
    name_contains: str = Form(""),
    performer_contains: str = Form(""),
    program_contains: str = Form(""),
    date_contains: str = Form(""),
    time_contains: str = Form(""),
    enabled: str | None = Form(None),
    db: Session = Depends(get_db),
):
    rule = NotificationRule(
        name_contains=name_contains.strip(),
        performer_contains=performer_contains.strip(),
        program_contains=program_contains.strip(),
        date_contains=date_contains.strip(),
        time_contains=time_contains.strip(),
        enabled=enabled == "on",
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/rules")
def api_create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    rule = NotificationRule(
        name_contains=payload.name_contains.strip(),
        performer_contains=payload.performer_contains.strip(),
        program_contains=payload.program_contains.strip(),
        date_contains=payload.date_contains.strip(),
        time_contains=payload.time_contains.strip(),
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"ok": True, "rule": _rule_to_dict(rule)}


@app.post("/rules/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(NotificationRule, rule_id)
    if rule:
        db.delete(rule)
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.delete("/api/rules/{rule_id}")
def api_delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(NotificationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()
    return {"ok": True}


@app.post("/scrape-now")
def scrape_now(db: Session = Depends(get_db)):
    scrape_job()
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/scrape-now")
def api_scrape_now(db: Session = Depends(get_db)):
    scrape_job()
    return {"ok": True}
