import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import logging

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, ensure_schema, get_db
from .entity_pipeline import (
    merge_entities,
    mark_unresolved_distinct,
    resolve_unresolved_with_existing,
    resolve_unresolved_with_new_entity,
)
from .logging_config import setup_logging
from .matching import normalize_candidate_pair
from .models import (
    Concert,
    DoNotMerge,
    Event,
    EventPerformer,
    EventWork,
    MatchSuggestion,
    MergeSuggestion,
    NotificationRule,
    Performer,
    PerformerAlias,
    UnresolvedEntity,
    Venue,
    VenueAlias,
    Work,
    ExtractionAudit,
)
from .scrapers import list_scrape_sources
from .scheduler import schedule_scraping, scrape_job
from .schemas import (
    ResolveUnresolvedRequest,
    RuleCreate,
    ScrapeNowRequest,
    SettingsUpdate,
    UpdateMergeSuggestionRequest,
)
from .services import backfill_concert_metadata, get_or_create_settings, scrape_and_persist


log_directory = setup_logging()
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Concert Dashboard")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _asset_version(*relative_paths: str) -> str:
    latest_mtime = 0
    for relative_path in relative_paths:
        path = Path(relative_path)
        if not path.exists():
            continue
        try:
            latest_mtime = max(latest_mtime, int(path.stat().st_mtime))
        except OSError:
            continue

    if latest_mtime <= 0:
        return datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return str(latest_mtime)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    started_at = perf_counter()

    logger.info(
        "request_started id=%s method=%s path=%s query=%s",
        request_id,
        request.method,
        request.url.path,
        str(request.url.query or ""),
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - started_at) * 1000
        logger.exception(
            "request_failed id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_finished id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


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
    logger.info("app_startup log_dir=%s", log_directory)
    db = SessionLocal()
    try:
        changed = backfill_concert_metadata(db)
        logger.info("metadata_backfill_complete changed=%s", changed)
    finally:
        db.close()

    schedule_scraping()
    logger.info("scheduler_initialized")


def _concert_to_dict(concert: Concert, normalized: dict | None = None) -> dict:
    normalized_payload = normalized or {
        "event_id": None,
        "title": "",
        "date": "",
        "sold_out": False,
        "price_tags": [],
        "venue": None,
        "performers": [],
        "works": [],
        "unresolved": {"performer": 0, "venue": 0, "work": 0, "total": 0},
    }

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
        "normalized": normalized_payload,
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
        "openrouter_api_key": settings.openrouter_api_key or "",
        "openrouter_model": settings.openrouter_model or "openai/gpt-4.1-mini",
        "openrouter_timeout_seconds": int(settings.openrouter_timeout_seconds or 40),
        "openrouter_max_retries": int(settings.openrouter_max_retries or 2),
    }


def _normalize_scrape_sources(raw_sources: list[str] | None) -> tuple[list[str], list[str]]:
    available_sources = set(list_scrape_sources())
    selected_sources: list[str] = []
    invalid_sources: list[str] = []

    for source in raw_sources or []:
        value = (source or "").strip()
        if not value:
            continue

        if value not in available_sources:
            invalid_sources.append(value)
            continue

        if value in selected_sources:
            continue

        selected_sources.append(value)

    return selected_sources, sorted(set(invalid_sources))


def _sanitize_positive_limit(value: int | None, max_allowed: int) -> int | None:
    if value is None or value <= 0:
        return None
    return min(int(value), max_allowed)


def _entity_label(db: Session, entity_type: str, entity_id: int | None) -> str:
    if entity_id is None:
        return ""

    if entity_type == "performer":
        performer = db.get(Performer, entity_id)
        return performer.canonical_name if performer else f"performer:{entity_id}"
    if entity_type == "venue":
        venue = db.get(Venue, entity_id)
        return venue.name if venue else f"venue:{entity_id}"
    if entity_type == "work":
        work = db.get(Work, entity_id)
        return f"{work.composer} - {work.title}" if work else f"work:{entity_id}"

    return f"{entity_type}:{entity_id}"


def _work_label(composer: str, title: str) -> str:
    composer_text = (composer or "").strip()
    title_text = (title or "").strip()
    if composer_text and title_text:
        return f"{composer_text} - {title_text}"
    return composer_text or title_text


def _build_normalized_concert_lookup(db: Session, concerts: list[Concert]) -> dict[int, dict]:
    concert_ids = [concert.id for concert in concerts if concert.id is not None]
    if not concert_ids:
        return {}

    events = db.scalars(select(Event).where(Event.concert_id.in_(concert_ids))).all()
    if not events:
        return {}

    event_by_concert = {event.concert_id: event for event in events if event.id is not None}
    event_ids = [event.id for event in events if event.id is not None]
    if not event_ids:
        return {}

    venue_ids = sorted({int(event.venue_id) for event in events if event.venue_id is not None})
    venue_map: dict[int, Venue] = {}
    if venue_ids:
        venues = db.scalars(select(Venue).where(Venue.id.in_(venue_ids))).all()
        venue_map = {venue.id: venue for venue in venues}

    performer_rows = db.execute(
        select(
            EventPerformer.event_id,
            EventPerformer.role,
            EventPerformer.confidence,
            Performer.id,
            Performer.canonical_name,
        )
        .join(Performer, Performer.id == EventPerformer.performer_id)
        .where(EventPerformer.event_id.in_(event_ids))
        .order_by(
            EventPerformer.event_id.asc(),
            EventPerformer.confidence.desc(),
            Performer.canonical_name.asc(),
        )
    ).all()

    performers_by_event: dict[int, list[dict]] = defaultdict(list)
    for event_id, role, confidence, performer_id, canonical_name in performer_rows:
        performers_by_event[int(event_id)].append(
            {
                "id": int(performer_id),
                "name": str(canonical_name or "").strip(),
                "role": str(role or "performer").strip() or "performer",
                "confidence": round(float(confidence or 0.0), 4),
            }
        )

    work_rows = db.execute(
        select(
            EventWork.event_id,
            EventWork.sequence_order,
            EventWork.confidence,
            Work.id,
            Work.composer,
            Work.title,
            Work.form,
            Work.number,
            Work.opus,
            Work.key,
        )
        .join(Work, Work.id == EventWork.work_id)
        .where(EventWork.event_id.in_(event_ids))
        .order_by(EventWork.event_id.asc(), EventWork.sequence_order.asc(), Work.composer.asc(), Work.title.asc())
    ).all()

    works_by_event: dict[int, list[dict]] = defaultdict(list)
    for event_id, sequence_order, confidence, work_id, composer, title, form, number, opus, key in work_rows:
        works_by_event[int(event_id)].append(
            {
                "id": int(work_id),
                "label": _work_label(str(composer or ""), str(title or "")),
                "composer": str(composer or "").strip(),
                "title": str(title or "").strip(),
                "form": str(form or "").strip(),
                "number": int(number) if number is not None else None,
                "opus": str(opus or "").strip(),
                "key": str(key or "").strip(),
                "sequence_order": int(sequence_order or 0),
                "confidence": round(float(confidence or 0.0), 4),
            }
        )

    unresolved_rows = db.execute(
        select(UnresolvedEntity.event_id, UnresolvedEntity.entity_type)
        .where(UnresolvedEntity.event_id.in_(event_ids))
        .where(UnresolvedEntity.status == "open")
    ).all()

    unresolved_by_event: dict[int, dict[str, int]] = defaultdict(lambda: {"performer": 0, "venue": 0, "work": 0})
    for event_id, entity_type in unresolved_rows:
        key = str(entity_type or "").strip().lower()
        if key not in {"performer", "venue", "work"}:
            continue
        unresolved_by_event[int(event_id)][key] += 1

    normalized_lookup: dict[int, dict] = {}
    for concert_id, event in event_by_concert.items():
        event_id = int(event.id)
        venue = venue_map.get(int(event.venue_id)) if event.venue_id is not None else None
        unresolved_counts = unresolved_by_event.get(event_id, {"performer": 0, "venue": 0, "work": 0})
        unresolved_total = (
            int(unresolved_counts.get("performer", 0))
            + int(unresolved_counts.get("venue", 0))
            + int(unresolved_counts.get("work", 0))
        )

        normalized_lookup[int(concert_id)] = {
            "event_id": event_id,
            "title": str(event.title or "").strip(),
            "date": str(event.date or "").strip(),
            "sold_out": bool(event.sold_out),
            "price_tags": [str(tag).strip() for tag in (event.price_tags or []) if str(tag).strip()],
            "venue": {"id": int(venue.id), "name": str(venue.name or "").strip()} if venue else None,
            "performers": performers_by_event.get(event_id, []),
            "works": works_by_event.get(event_id, []),
            "unresolved": {
                "performer": int(unresolved_counts.get("performer", 0)),
                "venue": int(unresolved_counts.get("venue", 0)),
                "work": int(unresolved_counts.get("work", 0)),
                "total": unresolved_total,
            },
        }

    return normalized_lookup


def _hydrate_candidates(db: Session, entity_type: str, candidates: list[dict]) -> list[dict]:
    hydrated: list[dict] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        try:
            candidate_id = int(candidate.get("id"))
        except (TypeError, ValueError):
            continue

        label = str(candidate.get("label", "") or "").strip() or _entity_label(db, entity_type, candidate_id)
        try:
            score = float(candidate.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        hydrated.append(
            {
                "id": candidate_id,
                "label": label,
                "score": round(max(0.0, min(1.0, score)), 4),
            }
        )

    hydrated.sort(key=lambda row: row["score"], reverse=True)
    return hydrated


def _unresolved_to_dict(db: Session, item: UnresolvedEntity) -> dict:
    event = db.get(Event, item.event_id)
    return {
        "id": item.id,
        "event_id": item.event_id,
        "event_title": event.title if event else "",
        "event_date": event.date if event else "",
        "concert_id": event.concert_id if event else None,
        "entity_type": item.entity_type,
        "raw_text": item.raw_text,
        "normalized_text": item.normalized_text or "",
        "candidates": _hydrate_candidates(db, item.entity_type, item.candidates_json or []),
        "status": item.status,
        "resolved_entity_id": item.resolved_entity_id,
        "resolved_entity_label": _entity_label(db, item.entity_type, item.resolved_entity_id),
        "resolution_action": item.resolution_action or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }


def _merge_suggestion_to_dict(db: Session, item: MergeSuggestion) -> dict:
    candidate_a_concert = _find_candidate_concert_link(db, item.entity_type, item.candidate_a_id)
    candidate_b_concert = _find_candidate_concert_link(db, item.entity_type, item.candidate_b_id)

    return {
        "id": item.id,
        "entity_type": item.entity_type,
        "candidate_a_id": item.candidate_a_id,
        "candidate_a_label": _entity_label(db, item.entity_type, item.candidate_a_id),
        "candidate_a_concert": candidate_a_concert,
        "candidate_b_id": item.candidate_b_id,
        "candidate_b_label": _entity_label(db, item.entity_type, item.candidate_b_id),
        "candidate_b_concert": candidate_b_concert,
        "score": item.score,
        "llm_assessment": item.llm_assessment or "",
        "confidence": item.confidence,
        "reason": item.reason or "",
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _find_candidate_concert_link(db: Session, entity_type: str, entity_id: int) -> dict | None:
    if entity_type == "performer":
        concert = db.scalar(
            select(Concert)
            .join(Event, Event.concert_id == Concert.id)
            .join(EventPerformer, EventPerformer.event_id == Event.id)
            .where(EventPerformer.performer_id == entity_id)
            .order_by(Concert.fetched_at.desc())
            .limit(1)
        )
    elif entity_type == "work":
        concert = db.scalar(
            select(Concert)
            .join(Event, Event.concert_id == Concert.id)
            .join(EventWork, EventWork.event_id == Event.id)
            .where(EventWork.work_id == entity_id)
            .order_by(Concert.fetched_at.desc())
            .limit(1)
        )
    elif entity_type == "venue":
        concert = db.scalar(
            select(Concert)
            .join(Event, Event.concert_id == Concert.id)
            .where(Event.venue_id == entity_id)
            .order_by(Concert.fetched_at.desc())
            .limit(1)
        )
    else:
        concert = None

    if concert is None:
        return None

    return {
        "id": concert.id,
        "name": concert.name,
        "source": concert.source,
        "source_url": concert.source_url,
        "date": concert.date_normalized or concert.date or "",
    }


def _build_concert_query(
    q: str = "",
    source: str = "",
    date_start: str = "",
    date_end: str = "",
    time_start: str = "",
    time_end: str = "",
    date_filter: str = "",
    performer_ids: list[int] | None = None,
    work_ids: list[int] | None = None,
    venue_ids: list[int] | None = None,
):
    query = select(Concert).order_by(Concert.fetched_at.desc())
    
    # Filter by specific performer IDs
    if performer_ids:
        performer_ids_filtered = [int(pid) for pid in performer_ids if int(pid) > 0]
        if performer_ids_filtered:
            performer_concert_ids = select(Event.concert_id).join(
                EventPerformer, EventPerformer.event_id == Event.id
            ).where(EventPerformer.performer_id.in_(performer_ids_filtered)).distinct()
            query = query.where(Concert.id.in_(performer_concert_ids))
    
    # Filter by specific work IDs
    if work_ids:
        work_ids_filtered = [int(wid) for wid in work_ids if int(wid) > 0]
        if work_ids_filtered:
            work_concert_ids = select(Event.concert_id).join(
                EventWork, EventWork.event_id == Event.id
            ).where(EventWork.work_id.in_(work_ids_filtered)).distinct()
            query = query.where(Concert.id.in_(work_concert_ids))
    
    # Filter by specific venue IDs
    if venue_ids:
        venue_ids_filtered = [int(vid) for vid in venue_ids if int(vid) > 0]
        if venue_ids_filtered:
            venue_concert_ids = select(Event.concert_id).where(Event.venue_id.in_(venue_ids_filtered))
            query = query.where(Concert.id.in_(venue_concert_ids))
    
    # Fuzzy text search
    if q:
        pattern = f"%{q}%"
        normalized_query = _normalize_text(q)
        normalized_pattern = f"%{normalized_query}%" if normalized_query else pattern

        performer_concert_ids = (
            select(Event.concert_id)
            .join(EventPerformer, EventPerformer.event_id == Event.id)
            .join(Performer, Performer.id == EventPerformer.performer_id)
            .outerjoin(PerformerAlias, PerformerAlias.performer_id == Performer.id)
            .where(
                or_(
                    Performer.canonical_name.like(pattern),
                    Performer.canonical_normalized.like(normalized_pattern),
                    PerformerAlias.alias.like(pattern),
                    PerformerAlias.normalized.like(normalized_pattern),
                )
            )
        )
        work_concert_ids = (
            select(Event.concert_id)
            .join(EventWork, EventWork.event_id == Event.id)
            .join(Work, Work.id == EventWork.work_id)
            .where(
                or_(
                    Work.title.like(pattern),
                    Work.composer.like(pattern),
                    Work.form.like(pattern),
                    Work.opus.like(pattern),
                    Work.key.like(pattern),
                    Work.title_normalized.like(normalized_pattern),
                    Work.composer_normalized.like(normalized_pattern),
                )
            )
        )
        venue_concert_ids = (
            select(Event.concert_id)
            .join(Venue, Venue.id == Event.venue_id)
            .outerjoin(VenueAlias, VenueAlias.venue_id == Venue.id)
            .where(
                or_(
                    Venue.name.like(pattern),
                    Venue.city.like(pattern),
                    Venue.name_normalized.like(normalized_pattern),
                    VenueAlias.alias.like(pattern),
                    VenueAlias.normalized.like(normalized_pattern),
                )
            )
        )
        event_title_concert_ids = select(Event.concert_id).where(Event.title.like(pattern))

        query = query.where(
            or_(
                Concert.name.like(pattern),
                Concert.program.like(pattern),
                Concert.performers.like(pattern),
                Concert.hall.like(pattern),
                Concert.id.in_(performer_concert_ids),
                Concert.id.in_(work_concert_ids),
                Concert.id.in_(venue_concert_ids),
                Concert.id.in_(event_title_concert_ids),
            )
        )
    if source:
        query = query.where(Concert.source == source)
    
    # Date range filtering (YYYY-MM-DD format)
    if date_start or date_end:
        date_conditions = []
        if date_start:
            date_conditions.append(Concert.date_normalized >= date_start)
        if date_end:
            date_conditions.append(Concert.date_normalized <= date_end)
        if date_conditions:
            query = query.where(and_(*date_conditions))
    
    # Time range filtering
    if time_start or time_end:
        time_conditions = []
        if time_start:
            time_conditions.append(Concert.time >= time_start)
        if time_end:
            time_conditions.append(Concert.time <= time_end)
        if time_conditions:
            query = query.where(and_(*time_conditions))
    
    # Backward compatibility: text-based date filter
    if date_filter:
        pattern = f"%{date_filter}%"
        normalized_date_concert_ids = select(Event.concert_id).where(Event.date.like(pattern))
        query = query.where(
            or_(
                Concert.date.like(pattern),
                Concert.date_normalized.like(pattern),
                Concert.id.in_(normalized_date_concert_ids),
            )
        )
    return query


def _delete_concert_records(db: Session, concert_ids: list[int]) -> int:
    unique_ids = sorted({int(concert_id) for concert_id in concert_ids if int(concert_id) > 0})
    if not unique_ids:
        return 0

    event_ids = db.scalars(select(Event.id).where(Event.concert_id.in_(unique_ids))).all()
    if event_ids:
        unresolved_ids = db.scalars(select(UnresolvedEntity.id).where(UnresolvedEntity.event_id.in_(event_ids))).all()
        if unresolved_ids:
            db.execute(delete(MatchSuggestion).where(MatchSuggestion.unresolved_entity_id.in_(unresolved_ids)))

        db.execute(delete(UnresolvedEntity).where(UnresolvedEntity.event_id.in_(event_ids)))
        db.execute(delete(EventPerformer).where(EventPerformer.event_id.in_(event_ids)))
        db.execute(delete(EventWork).where(EventWork.event_id.in_(event_ids)))
        db.execute(delete(ExtractionAudit).where(ExtractionAudit.event_id.in_(event_ids)))
        db.execute(delete(Event).where(Event.id.in_(event_ids)))

    db.execute(delete(ExtractionAudit).where(ExtractionAudit.concert_id.in_(unique_ids)))
    db.execute(delete(Concert).where(Concert.id.in_(unique_ids)))
    db.commit()
    return len(unique_ids)


def _get_dashboard_payload(
    db: Session,
    q: str = "",
    source: str = "",
    date_start: str = "",
    date_end: str = "",
    time_start: str = "",
    time_end: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    performer_ids: list[int] | None = None,
    work_ids: list[int] | None = None,
    venue_ids: list[int] | None = None,
) -> dict:
    settings = get_or_create_settings(db)

    query = _build_concert_query(
        q=q,
        source=source,
        date_start=date_start,
        date_end=date_end,
        time_start=time_start,
        time_end=time_end,
        date_filter=date_filter,
        performer_ids=performer_ids,
        work_ids=work_ids,
        venue_ids=venue_ids,
    )

    concerts = db.scalars(query.limit(2500)).all()
    normalized_lookup = _build_normalized_concert_lookup(db, concerts)
    concerts_payload = [_concert_to_dict(concert, normalized_lookup.get(concert.id)) for concert in concerts]

    if include_maybe:
        visible_concerts = concerts_payload
        maybe_hidden_count = 0
    else:
        visible_concerts = [concert for concert in concerts_payload if not concert["maybe_concert"]]
        maybe_hidden_count = len(concerts_payload) - len(visible_concerts)

    visible_concerts = visible_concerts[:500]
    rules = db.scalars(select(NotificationRule).order_by(NotificationRule.id.desc())).all()

    sources = sorted({concert["source"] for concert in visible_concerts if concert["source"]})

    # Build filter labels
    filter_labels = {"performers": {}, "works": {}, "venues": {}}
    if performer_ids:
        performers = db.scalars(select(Performer).where(Performer.id.in_(performer_ids))).all()
        filter_labels["performers"] = {p.id: p.canonical_name for p in performers}
    if work_ids:
        works = db.scalars(select(Work).where(Work.id.in_(work_ids))).all()
        filter_labels["works"] = {w.id: f"{w.composer} - {w.title}" if w.composer else w.title for w in works}
    if venue_ids:
        venues = db.scalars(select(Venue).where(Venue.id.in_(venue_ids))).all()
        filter_labels["venues"] = {v.id: v.name for v in venues}

    return {
        "concerts": visible_concerts,
        "rules": [_rule_to_dict(rule) for rule in rules],
        "settings": _settings_to_dict(settings),
        "filters": {
            "q": q,
            "source": source,
            "date_start": date_start,
            "date_end": date_end,
            "time_start": time_start,
            "time_end": time_end,
            "date_filter": date_filter,
            "include_maybe": include_maybe,
            "performer_ids": performer_ids or [],
            "work_ids": work_ids or [],
            "venue_ids": venue_ids or [],
        },
        "filter_labels": filter_labels,
        "maybe_hidden_count": maybe_hidden_count,
        "sources": sources,
        "scrape_sources": list_scrape_sources(),
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
        {
            "request": request,
            "asset_version": _asset_version("app/static/app.js", "app/static/styles.css"),
        },
    )


@app.get("/api/dashboard")
def api_dashboard(
    q: str = "",
    source: str = "",
    date_start: str = "",
    date_end: str = "",
    time_start: str = "",
    time_end: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    performer_ids: str = "",
    work_ids: str = "",
    venue_ids: str = "",
    db: Session = Depends(get_db),
):
    # Parse comma-separated IDs
    performer_id_list = [int(x) for x in performer_ids.split(",") if x.strip().isdigit()] if performer_ids else None
    work_id_list = [int(x) for x in work_ids.split(",") if x.strip().isdigit()] if work_ids else None
    venue_id_list = [int(x) for x in venue_ids.split(",") if x.strip().isdigit()] if venue_ids else None

    return _get_dashboard_payload(
        db,
        q=q,
        source=source,
        date_start=date_start,
        date_end=date_end,
        time_start=time_start,
        time_end=time_end,
        date_filter=date_filter,
        include_maybe=include_maybe,
        performer_ids=performer_id_list,
        work_ids=work_id_list,
        venue_ids=venue_id_list,
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
    openrouter_api_key: str = Form(""),
    openrouter_model: str = Form("openai/gpt-4.1-mini"),
    openrouter_timeout_seconds: int = Form(40),
    openrouter_max_retries: int = Form(2),
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
    settings.openrouter_api_key = openrouter_api_key.strip()
    settings.openrouter_model = openrouter_model.strip() or "openai/gpt-4.1-mini"
    settings.openrouter_timeout_seconds = max(5, openrouter_timeout_seconds)
    settings.openrouter_max_retries = max(0, openrouter_max_retries)
    db.commit()
    logger.info(
        "settings_updated scrape_interval_minutes=%s notifications_enabled=%s",
        settings.scrape_interval_minutes,
        settings.notifications_enabled,
    )

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
    settings.openrouter_api_key = payload.openrouter_api_key.strip()
    settings.openrouter_model = payload.openrouter_model.strip() or "openai/gpt-4.1-mini"
    settings.openrouter_timeout_seconds = max(5, int(payload.openrouter_timeout_seconds))
    settings.openrouter_max_retries = max(0, int(payload.openrouter_max_retries))
    db.commit()
    logger.info(
        "settings_updated_via_api scrape_interval_minutes=%s notifications_enabled=%s",
        settings.scrape_interval_minutes,
        settings.notifications_enabled,
    )

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
    logger.info("rule_created id=%s enabled=%s", rule.id, rule.enabled)
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
    logger.info("rule_created_via_api id=%s enabled=%s", rule.id, rule.enabled)
    return {"ok": True, "rule": _rule_to_dict(rule)}


@app.post("/rules/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(NotificationRule, rule_id)
    if rule:
        logger.info("rule_deleted id=%s", rule_id)
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
    logger.info("rule_deleted_via_api id=%s", rule_id)
    return {"ok": True}


@app.post("/scrape-now")
def scrape_now(db: Session = Depends(get_db)):
    logger.info("manual_scrape_triggered source=form")
    scrape_job()
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/scrape-now")
def api_scrape_now(payload: ScrapeNowRequest | None = Body(default=None), db: Session = Depends(get_db)):
    selected_sources, invalid_sources = _normalize_scrape_sources(payload.sources if payload else None)
    if invalid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported sources: {', '.join(invalid_sources)}",
        )

    max_per_source = _sanitize_positive_limit(payload.max_per_source if payload else None, max_allowed=1000)
    max_total = _sanitize_positive_limit(payload.max_total if payload else None, max_allowed=5000)

    logger.info(
        "manual_scrape_triggered source=api selected_sources=%s max_per_source=%s max_total=%s",
        selected_sources or ["all"],
        max_per_source,
        max_total,
    )

    inserted = scrape_and_persist(
        db,
        sources=selected_sources or None,
        max_per_source=max_per_source,
        max_total=max_total,
    )

    return {
        "ok": True,
        "inserted": inserted,
        "applied": {
            "sources": selected_sources or list_scrape_sources(),
            "max_per_source": max_per_source,
            "max_total": max_total,
        },
    }


@app.get("/api/scrape/sources")
def api_scrape_sources():
    return {"sources": list_scrape_sources()}


@app.get("/api/search/suggestions")
def api_search_suggestions(q: str = "", limit: int = 10, db: Session = Depends(get_db)):
    """
    Get search suggestions based on normalized entries.
    Returns matching performers, works, and venues.
    """
    if not q or not q.strip():
        return {"suggestions": [], "query": q}
    
    safe_limit = max(1, min(limit, 50))
    search_pattern = f"%{q}%"
    normalized_pattern = f"%{_normalize_text(q)}%"
    
    suggestions = []
    
    # Get matching performers
    performers = db.scalars(
        select(Performer)
        .where(
            or_(
                Performer.canonical_name.ilike(search_pattern),
                Performer.canonical_normalized.ilike(normalized_pattern),
            )
        )
        .limit(safe_limit)
    ).all()
    
    for performer in performers:
        suggestions.append({
            "type": "performer",
            "id": performer.id,
            "label": performer.canonical_name,
            "normalized": performer.canonical_normalized,
            "native_name": performer.native_name or "",
        })
    
    # Get matching performer aliases
    if len(suggestions) < safe_limit:
        performer_aliases = db.execute(
            select(PerformerAlias, Performer)
            .join(Performer, Performer.id == PerformerAlias.performer_id)
            .where(
                or_(
                    PerformerAlias.alias.ilike(search_pattern),
                    PerformerAlias.normalized.ilike(normalized_pattern),
                )
            )
            .limit(safe_limit - len(suggestions))
        ).all()
        
        for alias_row, performer in performer_aliases:
            # Avoid duplicates
            if not any(s["type"] == "performer" and s["id"] == performer.id for s in suggestions):
                suggestions.append({
                    "type": "performer",
                    "id": performer.id,
                    "label": performer.canonical_name,
                    "normalized": performer.canonical_normalized,
                    "native_name": performer.native_name or "",
                    "matched_alias": alias_row.alias,
                })
    
    # Get matching works
    if len(suggestions) < safe_limit * 2:
        works = db.scalars(
            select(Work)
            .where(
                or_(
                    Work.title.ilike(search_pattern),
                    Work.composer.ilike(search_pattern),
                    Work.form.ilike(search_pattern),
                    Work.title_normalized.ilike(normalized_pattern),
                    Work.composer_normalized.ilike(normalized_pattern),
                )
            )
            .limit(safe_limit - (len(suggestions) // 2))
        ).all()
        
        for work in works:
            suggestions.append({
                "type": "work",
                "id": work.id,
                "label": f"{work.composer} - {work.title}" if work.composer else work.title,
                "composer": work.composer,
                "composer_normalized": work.composer_normalized,
                "title": work.title,
                "title_normalized": work.title_normalized,
                "form": work.form,
                "opus": work.opus,
            })
    
    # Get matching venues
    if len(suggestions) < safe_limit * 3:
        venues = db.scalars(
            select(Venue)
            .where(
                or_(
                    Venue.name.ilike(search_pattern),
                    Venue.city.ilike(search_pattern),
                    Venue.name_normalized.ilike(normalized_pattern),
                )
            )
            .limit(safe_limit - (len(suggestions) // 3))
        ).all()
        
        for venue in venues:
            suggestions.append({
                "type": "venue",
                "id": venue.id,
                "label": f"{venue.name}" + (f", {venue.city}" if venue.city else ""),
                "name": venue.name,
                "city": venue.city or "",
                "name_normalized": venue.name_normalized,
            })
    
    # Get matching venue aliases
    if len(suggestions) < safe_limit * 4:
        venue_aliases = db.execute(
            select(VenueAlias, Venue)
            .join(Venue, Venue.id == VenueAlias.venue_id)
            .where(
                or_(
                    VenueAlias.alias.ilike(search_pattern),
                    VenueAlias.normalized.ilike(normalized_pattern),
                )
            )
            .limit(safe_limit - len(suggestions))
        ).all()
        
        for alias_row, venue in venue_aliases:
            # Avoid duplicates
            if not any(s["type"] == "venue" and s["id"] == venue.id for s in suggestions):
                suggestions.append({
                    "type": "venue",
                    "id": venue.id,
                    "label": f"{venue.name}" + (f", {venue.city}" if venue.city else ""),
                    "name": venue.name,
                    "city": venue.city or "",
                    "name_normalized": venue.name_normalized,
                    "matched_alias": alias_row.alias,
                })
    
    return {
        "suggestions": suggestions[:safe_limit * 4],
        "query": q,
        "count": len(suggestions[:safe_limit * 4]),
    }


@app.get("/api/concerts/dump")
def api_dump_concerts(
    q: str = "",
    source: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(limit, 20000))
    concerts = db.scalars(_build_concert_query(q=q, source=source, date_filter=date_filter).limit(safe_limit)).all()
    items = [_concert_to_dict(concert) for concert in concerts]
    if not include_maybe:
        items = [item for item in items if not item["maybe_concert"]]

    return {
        "items": items,
        "count": len(items),
        "limit": safe_limit,
        "filters": {
            "q": q,
            "source": source,
            "date_filter": date_filter,
            "include_maybe": include_maybe,
        },
        "exported_at": datetime.utcnow().isoformat(),
    }


@app.delete("/api/concerts/{concert_id}")
def api_delete_concert(concert_id: int, db: Session = Depends(get_db)):
    concert = db.get(Concert, concert_id)
    if not concert:
        raise HTTPException(status_code=404, detail="Concert not found")

    deleted_count = _delete_concert_records(db, [concert_id])
    logger.info("concert_deleted concert_id=%s", concert_id)
    return {"ok": True, "deleted": deleted_count, "mode": "single"}


@app.delete("/api/concerts")
def api_delete_concerts(
    mode: str = "filtered",
    q: str = "",
    source: str = "",
    date_filter: str = "",
    include_maybe: bool = False,
    db: Session = Depends(get_db),
):
    normalized_mode = (mode or "filtered").strip().lower()
    if normalized_mode not in {"filtered", "all"}:
        raise HTTPException(status_code=400, detail="mode must be either 'filtered' or 'all'")

    if normalized_mode == "all":
        concert_ids = db.scalars(select(Concert.id)).all()
    else:
        concerts = db.scalars(_build_concert_query(q=q, source=source, date_filter=date_filter)).all()
        if include_maybe:
            concert_ids = [concert.id for concert in concerts]
        else:
            concert_ids = [concert.id for concert in concerts if not _is_maybe_concert(concert)]

    deleted_count = _delete_concert_records(db, concert_ids)
    logger.info(
        "concerts_deleted mode=%s deleted=%s q=%s source=%s date_filter=%s include_maybe=%s",
        normalized_mode,
        deleted_count,
        q,
        source,
        date_filter,
        include_maybe,
    )

    return {
        "ok": True,
        "deleted": deleted_count,
        "mode": normalized_mode,
    }


@app.get("/api/resolution/unresolved")
def api_list_unresolved(
    include_closed: bool = False,
    entity_type: str = "",
    db: Session = Depends(get_db),
):
    query = select(UnresolvedEntity).order_by(UnresolvedEntity.created_at.desc())
    if not include_closed:
        query = query.where(UnresolvedEntity.status == "open")
    if entity_type:
        query = query.where(UnresolvedEntity.entity_type == entity_type)

    rows = db.scalars(query.limit(1000)).all()
    return {
        "items": [_unresolved_to_dict(db, item) for item in rows],
        "count": len(rows),
    }


@app.post("/api/resolution/unresolved/{unresolved_id}")
def api_resolve_unresolved(
    unresolved_id: int,
    payload: ResolveUnresolvedRequest,
    db: Session = Depends(get_db),
):
    unresolved = db.get(UnresolvedEntity, unresolved_id)
    if not unresolved:
        raise HTTPException(status_code=404, detail="Unresolved entity not found")

    if unresolved.status != "open":
        raise HTTPException(status_code=400, detail="Unresolved entity is not open")

    if payload.action == "accept_candidate":
        if payload.candidate_id is None:
            raise HTTPException(status_code=400, detail="candidate_id is required for accept_candidate")
        resolve_unresolved_with_existing(db, unresolved, payload.candidate_id)
    elif payload.action == "create_new":
        value = payload.value.strip() or unresolved.raw_text
        created_id = resolve_unresolved_with_new_entity(db, unresolved, value)
        if created_id is None:
            raise HTTPException(status_code=400, detail="Could not create entity for unresolved item")
    elif payload.action == "mark_distinct":
        mark_unresolved_distinct(db, unresolved, payload.candidate_id, payload.reason.strip())

    linked_suggestions = db.scalars(
        select(MatchSuggestion).where(MatchSuggestion.unresolved_entity_id == unresolved.id)
    ).all()
    selected_candidate_id = unresolved.resolved_entity_id
    for suggestion in linked_suggestions:
        suggestion.status = "resolved"
        suggestion.selected_candidate_id = selected_candidate_id
        suggestion.resolved_at = datetime.utcnow()
        db.add(suggestion)

    unresolved.resolved_at = datetime.utcnow()
    db.add(unresolved)
    db.commit()
    db.refresh(unresolved)
    logger.info("unresolved_resolved id=%s action=%s", unresolved.id, payload.action)

    return {"ok": True, "item": _unresolved_to_dict(db, unresolved)}


@app.get("/api/resolution/merge-suggestions")
def api_list_merge_suggestions(
    include_closed: bool = False,
    entity_type: str = "",
    db: Session = Depends(get_db),
):
    query = select(MergeSuggestion).order_by(MergeSuggestion.created_at.desc())
    if not include_closed:
        query = query.where(MergeSuggestion.status == "pending")
    if entity_type:
        query = query.where(MergeSuggestion.entity_type == entity_type)

    rows = db.scalars(query.limit(1000)).all()
    return {
        "items": [_merge_suggestion_to_dict(db, item) for item in rows],
        "count": len(rows),
    }


@app.post("/api/resolution/merge-suggestions/{suggestion_id}")
def api_update_merge_suggestion(
    suggestion_id: int,
    payload: UpdateMergeSuggestionRequest,
    db: Session = Depends(get_db),
):
    suggestion = db.get(MergeSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Merge suggestion not found")

    if suggestion.status != "pending":
        raise HTTPException(status_code=400, detail="Merge suggestion is not pending")

    now = datetime.utcnow()
    if payload.action == "merge":
        merged_ids = merge_entities(
            db,
            suggestion.entity_type,
            suggestion.candidate_a_id,
            suggestion.candidate_b_id,
        )
        if merged_ids is None:
            raise HTTPException(status_code=400, detail="Could not merge entities for this suggestion")

        keep_id, drop_id = merged_ids
        suggestion.status = "merged"
        suggestion.reason = payload.reason.strip() or suggestion.reason

        linked_suggestions = db.scalars(
            select(MergeSuggestion)
            .where(MergeSuggestion.status == "pending")
            .where(MergeSuggestion.id != suggestion.id)
            .where(
                or_(
                    MergeSuggestion.candidate_a_id == drop_id,
                    MergeSuggestion.candidate_b_id == drop_id,
                )
            )
        ).all()
        for linked in linked_suggestions:
            linked.status = "rejected"
            linked.reason = f"auto-closed after merge into {keep_id}"
            linked.reviewed_at = now
            db.add(linked)
    elif payload.action == "reject":
        suggestion.status = "rejected"
        suggestion.reason = payload.reason.strip() or suggestion.reason
    elif payload.action == "do_not_merge":
        suggestion.status = "do_not_merge"
        suggestion.reason = payload.reason.strip() or suggestion.reason

        entity_type, left_id, right_id = normalize_candidate_pair(
            suggestion.entity_type,
            suggestion.candidate_a_id,
            suggestion.candidate_b_id,
        )
        exists = db.scalar(
            select(DoNotMerge)
            .where(DoNotMerge.entity_type == entity_type)
            .where(DoNotMerge.entity_id_a == left_id)
            .where(DoNotMerge.entity_id_b == right_id)
            .limit(1)
        )
        if not exists:
            db.add(
                DoNotMerge(
                    entity_type=entity_type,
                    entity_id_a=left_id,
                    entity_id_b=right_id,
                    reason=payload.reason.strip() or "manual do_not_merge decision",
                )
            )

    suggestion.reviewed_at = now
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    logger.info("merge_suggestion_updated id=%s action=%s", suggestion.id, payload.action)

    return {"ok": True, "item": _merge_suggestion_to_dict(db, suggestion)}
