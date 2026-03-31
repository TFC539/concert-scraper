from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Concert, NotificationRule
from .scheduler import schedule_scraping, scrape_job
from .services import get_or_create_settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Concert Dashboard")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    schedule_scraping()


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    q: str = "",
    source: str = "",
    date_filter: str = "",
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db)

    query = select(Concert).order_by(Concert.fetched_at.desc())
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Concert.name.like(pattern),
                Concert.program.like(pattern),
                Concert.performers.like(pattern),
            )
        )
    if source:
        query = query.where(Concert.source == source)
    if date_filter:
        query = query.where(Concert.date.like(f"%{date_filter}%"))

    concerts = db.scalars(query.limit(500)).all()
    rules = db.scalars(select(NotificationRule).order_by(NotificationRule.id.desc())).all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "concerts": concerts,
            "settings": settings,
            "rules": rules,
            "filters": {"q": q, "source": source, "date_filter": date_filter},
        },
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


@app.post("/rules/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(NotificationRule, rule_id)
    if rule:
        db.delete(rule)
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/scrape-now")
def scrape_now(db: Session = Depends(get_db)):
    scrape_job()
    return RedirectResponse(url="/", status_code=303)
