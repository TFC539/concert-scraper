from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .matching import (
    AMBIGUOUS_THRESHOLD,
    MatchResult,
    add_performer_alias,
    add_venue_alias,
    create_performer,
    create_venue,
    create_work,
    match_performer,
    match_venue,
    match_work,
    normalize_candidate_pair,
    pretty_label_for_unresolved,
)
from .models import (
    AppSettings,
    Concert,
    DoNotMerge,
    Event,
    EventPerformer,
    EventWork,
    ExtractionAudit,
    MatchSuggestion,
    MergeSuggestion,
    Performer,
    PerformerAlias,
    UnresolvedEntity,
    Venue,
    VenueAlias,
    Work,
)
from .normalization import normalize_venue
from .openrouter_client import (
    OpenRouterDisambiguationError,
    OpenRouterExtractionError,
    disambiguate_with_openrouter,
    extract_with_openrouter,
    fallback_extract_from_flat_fields,
    load_openrouter_config,
)


logger = logging.getLogger(__name__)


def _preview_text(value: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


@dataclass
class PipelineResult:
    event_id: int
    matched_performers: int
    matched_works: int
    unresolved_count: int


def build_raw_extraction_text(concert: Concert) -> str:
    performer_parts = [
        part.strip()
        for part in re.split(r"\n+|\s*\|\s*|\s*;\s*", str(concert.performers or ""))
        if part and part.strip()
    ]
    program_parts = [
        part.strip()
        for part in re.split(r"\n+|\s*\|\s*", str(concert.program or ""))
        if part and part.strip()
    ]

    ticketing_matches: list[str] = []
    for candidate in [concert.program or "", concert.name or "", concert.time or ""]:
        text = str(candidate or "")
        if not text:
            continue

        for match in re.findall(
            r"(?:\bsold\s*-?\s*out\b|\bausverkauft\b|remaining tickets(?:[^\n|]{0,90})|(?:€|\bEUR\b|\bCHF\b|\$)\s*\d+[\d.,]*|\d+[\d.,]*\s*(?:€|\bEUR\b|\bCHF\b|\$)|\bfree\b)",
            text,
            flags=re.IGNORECASE,
        ):
            cleaned = re.sub(r"\s+", " ", match).strip()
            if cleaned:
                ticketing_matches.append(cleaned)

    ticketing_parts: list[str] = []
    seen_ticketing: set[str] = set()
    for item in ticketing_matches:
        key = item.casefold()
        if key in seen_ticketing:
            continue
        seen_ticketing.add(key)
        ticketing_parts.append(item)

    ticketing_text = " | ".join(ticketing_parts)

    lines: list[str] = [
        "Event Metadata:",
        f"Name: {concert.name or ''}",
        f"Venue: {concert.hall or ''}",
        f"Date: {concert.date_normalized or concert.date or ''}",
        f"Time: {concert.time or ''}",
        f"Ticketing: {ticketing_text}",
        f"Source: {concert.source or ''}",
        f"Source URL: {concert.source_url or ''}",
        "",
        "Performers:",
    ]

    if performer_parts:
        lines.extend(f"- {part}" for part in performer_parts)
    else:
        lines.append("- ")

    lines.extend(["", "Programme:"])
    if program_parts:
        lines.extend(f"- {part}" for part in program_parts)
    else:
        lines.append("- ")

    return "\n".join(lines)


def _upsert_event(db: Session, concert: Concert) -> Event:
    event = db.scalar(select(Event).where(Event.concert_id == concert.id).limit(1))
    if event is None:
        event = Event(
            concert_id=concert.id,
            title=concert.name,
            date=concert.date_normalized or concert.date,
            sold_out=False,
            price_tags=[],
        )
        db.add(event)
        db.flush()
    else:
        event.title = concert.name
        event.date = concert.date_normalized or concert.date
        db.add(event)
        db.flush()

    return event


def _reset_event_entities(db: Session, event_id: int) -> None:
    unresolved_ids = db.scalars(select(UnresolvedEntity.id).where(UnresolvedEntity.event_id == event_id)).all()
    if unresolved_ids:
        db.execute(delete(MatchSuggestion).where(MatchSuggestion.unresolved_entity_id.in_(unresolved_ids)))

    db.execute(delete(UnresolvedEntity).where(UnresolvedEntity.event_id == event_id))
    db.execute(delete(EventPerformer).where(EventPerformer.event_id == event_id))
    db.execute(delete(EventWork).where(EventWork.event_id == event_id))


def _record_audit(
    db: Session,
    concert_id: int,
    event_id: int,
    model: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    success: bool,
    error_message: str,
) -> None:
    db.add(
        ExtractionAudit(
            concert_id=concert_id,
            event_id=event_id,
            provider="openrouter",
            model=model,
            request_payload=request_payload,
            response_payload=response_payload,
            success=success,
            error_message=error_message,
        )
    )


def _create_unresolved(
    db: Session,
    event_id: int,
    entity_type: str,
    raw_text: str,
    normalized_text: str,
    candidates: list[dict[str, Any]],
    confidence_score: float,
    triage_bucket: str,
    status: str,
    review_priority: int,
) -> None:
    logger.warning(
        "entity_unresolved_created event_id=%s entity_type=%s raw_text_preview=%s normalized_text=%s candidate_count=%s",
        event_id,
        entity_type,
        _preview_text(raw_text),
        normalized_text,
        len(candidates or []),
    )
    unresolved = UnresolvedEntity(
        event_id=event_id,
        entity_type=entity_type,
        raw_text=raw_text,
        normalized_text=normalized_text,
        candidates_json=candidates,
        status=status,
        triage_bucket=triage_bucket,
        confidence_score=max(0.0, min(1.0, float(confidence_score or 0.0))),
        review_priority=max(1, int(review_priority or 1000)),
    )
    db.add(unresolved)
    db.flush()

    db.add(
        MatchSuggestion(
            unresolved_entity_id=unresolved.id,
            entity_type=entity_type,
            input_text=raw_text,
            candidates_json=candidates,
            status="pending",
        )
    )


def _triage_from_match_result(status: str, confidence_score: float) -> tuple[str, str, int]:
    confidence = max(0.0, min(1.0, float(confidence_score or 0.0)))
    if status == "ambiguous" or confidence >= 0.9:
        review_priority = 500 + int((1.0 - confidence) * 300)
        return "medium", "deferred", review_priority

    review_priority = 100 + int((1.0 - confidence) * 900)
    return "critical", "open", review_priority


def _maybe_add_merge_suggestion(
    db: Session,
    entity_type: str,
    candidate_a_id: int,
    candidate_b_id: int,
    score: float,
    reason: str,
) -> None:
    if candidate_a_id == candidate_b_id:
        return

    entity_type, left_id, right_id = normalize_candidate_pair(entity_type, candidate_a_id, candidate_b_id)

    blocked = db.scalar(
        select(DoNotMerge)
        .where(DoNotMerge.entity_type == entity_type)
        .where(DoNotMerge.entity_id_a == left_id)
        .where(DoNotMerge.entity_id_b == right_id)
        .limit(1)
    )
    if blocked:
        return

    existing = db.scalar(
        select(MergeSuggestion)
        .where(MergeSuggestion.entity_type == entity_type)
        .where(MergeSuggestion.candidate_a_id == left_id)
        .where(MergeSuggestion.candidate_b_id == right_id)
        .where(MergeSuggestion.status == "pending")
        .limit(1)
    )
    if existing:
        return

    db.add(
        MergeSuggestion(
            entity_type=entity_type,
            candidate_a_id=left_id,
            candidate_b_id=right_id,
            score=score,
            llm_assessment="",
            confidence=max(0.0, min(1.0, score - 0.25)),
            reason=reason,
            status="pending",
        )
    )


def _queue_performer_merge_suggestions(db: Session, performer_id: int) -> None:
    base = db.get(Performer, performer_id)
    if base is None:
        return

    candidates = db.scalars(select(Performer).where(Performer.id != performer_id).limit(2000)).all()
    for other in candidates:
        similarity = 0.0
        left = base.canonical_normalized
        right = other.canonical_normalized
        if left and right:
            common_tokens = set(left.split()) & set(right.split())
            if common_tokens:
                similarity = len(common_tokens) / max(len(set(left.split()) | set(right.split())), 1)

        if 0.5 <= similarity <= 0.95:
            _maybe_add_merge_suggestion(
                db,
                "performer",
                base.id,
                other.id,
                similarity,
                "Token overlap suggests possible duplicate performer records",
            )


def _queue_venue_merge_suggestions(db: Session, venue_id: int) -> None:
    base = db.get(Venue, venue_id)
    if base is None:
        return

    candidates = db.scalars(select(Venue).where(Venue.id != venue_id).limit(1000)).all()
    for other in candidates:
        left = normalize_venue(base.name)
        right = normalize_venue(other.name)
        if not left or not right:
            continue
        similarity = 1.0 if left == right else 0.0
        if not similarity:
            overlap = set(left.split()) & set(right.split())
            if overlap:
                similarity = len(overlap) / max(len(set(left.split()) | set(right.split())), 1)

        if 0.6 <= similarity <= 0.95:
            _maybe_add_merge_suggestion(
                db,
                "venue",
                base.id,
                other.id,
                similarity,
                "Venue name overlap suggests potential duplicate venue records",
            )


def _normalize_extraction(extracted: dict[str, Any]) -> dict[str, Any]:
    def _split_compound_text(value: str) -> list[str]:
        parts = re.split(
            r"\n+|\s*\|\s*|\s*;\s*|\s*/\s*|\s*&\s*|\s+[Uu][Nn][Dd]\s+|\s+[Aa][Nn][Dd]\s+",
            str(value or ""),
        )
        output: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = str(part or "").strip(" \t,.-")
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            output.append(text)
        return output

    performers: list[str] = []
    seen_performers: set[str] = set()
    for item in extracted.get("p", []):
        for text in _split_compound_text(str(item or "")):
            key = text.casefold()
            if key in seen_performers:
                continue
            seen_performers.add(key)
            performers.append(text)

    works: list[dict[str, str]] = []
    seen_works: set[tuple[str, str]] = set()
    for item in extracted.get("w", []):
        if not isinstance(item, dict):
            continue
        composer = str(item.get("c", "") or "").strip()
        title = str(item.get("t", "") or "").strip()

        if not composer and title:
            split_candidate = re.match(r"^([^:]{2,120})\s*:\s*(.+)$", title)
            if split_candidate:
                composer = split_candidate.group(1).strip()
                title = split_candidate.group(2).strip()

        title_parts = _split_compound_text(title) if title else [""]
        for title_part in title_parts:
            if not composer and not title_part:
                continue
            dedupe_key = (composer.casefold(), title_part.casefold())
            if dedupe_key in seen_works:
                continue
            seen_works.add(dedupe_key)
            works.append({"c": composer, "t": title_part})

    venue = str(extracted.get("v", "") or "").strip()
    date_text = str(extracted.get("d", "") or "").strip()
    sold_out = bool(extracted.get("s", False))

    price_tags: list[str] = []
    seen_price_tags: set[str] = set()
    for item in extracted.get("pt", []):
        value = str(item or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen_price_tags:
            continue
        seen_price_tags.add(key)
        price_tags.append(value)

    return {
        "p": performers,
        "w": works,
        "v": venue,
        "d": date_text,
        "s": sold_out,
        "pt": price_tags,
    }


def _resolve_ambiguous_with_llm(
    entity_type: str,
    raw_text: str,
    match_result: MatchResult,
    config: Any | None,
) -> tuple[int | None, float]:
    if match_result.status != "ambiguous" or not config or not match_result.candidates:
        return None, 0.0

    logger.info(
        "entity_disambiguation_started entity_type=%s raw_text_preview=%s candidate_count=%s",
        entity_type,
        _preview_text(raw_text),
        len(match_result.candidates),
    )

    try:
        disambiguation_payload, _, _ = disambiguate_with_openrouter(
            entity_type=entity_type,
            raw_text=raw_text,
            candidates=match_result.candidates,
            config=config,
        )
    except OpenRouterDisambiguationError as exc:
        logger.warning(
            "entity_disambiguation_failed entity_type=%s raw_text=%s error=%s",
            entity_type,
            raw_text,
            str(exc),
        )
        return None, 0.0

    selected_id = disambiguation_payload.get("id")
    confidence = float(disambiguation_payload.get("confidence", 0.0) or 0.0)
    if selected_id is None:
        logger.info(
            "entity_disambiguation_no_selection entity_type=%s confidence=%.3f",
            entity_type,
            confidence,
        )
        return None, confidence

    candidate_ids = {
        int(candidate["id"])
        for candidate in match_result.candidates
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }
    if selected_id not in candidate_ids:
        logger.warning(
            "entity_disambiguation_invalid_candidate entity_type=%s selected_id=%s",
            entity_type,
            selected_id,
        )
        return None, confidence

    if confidence < AMBIGUOUS_THRESHOLD:
        logger.info(
            "entity_disambiguation_below_threshold entity_type=%s selected_id=%s confidence=%.3f threshold=%.3f",
            entity_type,
            selected_id,
            confidence,
            AMBIGUOUS_THRESHOLD,
        )
        return None, confidence

    logger.info(
        "entity_disambiguation_selected entity_type=%s selected_id=%s confidence=%.3f",
        entity_type,
        selected_id,
        confidence,
    )

    return selected_id, confidence


def _promote_ambiguous_match_if_possible(
    entity_type: str,
    raw_text: str,
    match_result: MatchResult,
    config: Any | None,
) -> MatchResult:
    if match_result.status != "ambiguous":
        return match_result

    selected_id, llm_confidence = _resolve_ambiguous_with_llm(
        entity_type=entity_type,
        raw_text=raw_text,
        match_result=match_result,
        config=config,
    )
    if selected_id is None:
        return match_result

    selected_candidate = None
    for candidate in match_result.candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            candidate_id = int(candidate.get("id"))
        except (TypeError, ValueError):
            continue
        if candidate_id == selected_id:
            selected_candidate = candidate
            break
    candidates = [selected_candidate] if selected_candidate else match_result.candidates
    confidence = max(float(match_result.confidence or 0.0), float(llm_confidence or 0.0))
    return MatchResult(
        status="matched",
        entity_id=selected_id,
        confidence=max(0.0, min(1.0, confidence)),
        normalized_text=match_result.normalized_text,
        candidates=candidates,
    )


def process_concert_entity_pipeline(db: Session, concert: Concert) -> PipelineResult:
    logger.info("entity_pipeline_started concert_id=%s source=%s", concert.id, concert.source)
    event = _upsert_event(db, concert)
    _reset_event_entities(db, event.id)

    raw_text = build_raw_extraction_text(concert)
    logger.info(
        "entity_pipeline_raw_text_ready concert_id=%s chars=%s lines=%s preview=%s",
        concert.id,
        len(raw_text),
        len(raw_text.splitlines()),
        _preview_text(raw_text),
    )
    settings = db.scalar(select(AppSettings).limit(1))
    config_overrides: dict[str, Any] | None = None
    if settings is not None:
        config_overrides = {
            "api_key": settings.openrouter_api_key or "",
            "model": settings.openrouter_model or "",
            "timeout_seconds": settings.openrouter_timeout_seconds,
            "max_retries": settings.openrouter_max_retries,
        }
    config = load_openrouter_config(config_overrides)
    logger.info(
        "entity_pipeline_config_ready concert_id=%s has_openrouter_config=%s configured_model=%s",
        concert.id,
        bool(config),
        config.model if config else "",
    )

    extracted: dict[str, Any]
    request_payload: dict[str, Any] = {}
    response_payload: dict[str, Any] = {}
    extraction_success = False
    extraction_error = ""
    model_name = config.model if config else "fallback"

    if config:
        try:
            extracted, request_payload, response_payload = extract_with_openrouter(raw_text, config)
            extraction_success = True
            logger.info("entity_extraction_success concert_id=%s model=%s", concert.id, config.model)
        except OpenRouterExtractionError as exc:
            extraction_error = str(exc)
            logger.warning("entity_extraction_failed_fallback concert_id=%s error=%s", concert.id, extraction_error)
            extracted = fallback_extract_from_flat_fields(
                {
                    "name": concert.name,
                    "performers": concert.performers,
                    "program": concert.program,
                    "hall": concert.hall,
                    "date": concert.date,
                    "date_normalized": concert.date_normalized,
                }
            )
    else:
        extraction_error = "OPENROUTER_API_KEY not configured; fallback extraction used"
        logger.info("entity_extraction_fallback_no_api_key concert_id=%s", concert.id)
        extracted = fallback_extract_from_flat_fields(
            {
                "name": concert.name,
                "performers": concert.performers,
                "program": concert.program,
                "hall": concert.hall,
                "date": concert.date,
                "date_normalized": concert.date_normalized,
            }
        )

    extracted = _normalize_extraction(extracted)
    logger.info(
        "entity_extraction_normalized concert_id=%s performers=%s works=%s has_venue=%s has_date=%s sold_out=%s price_tags=%s",
        concert.id,
        len(extracted.get("p", [])),
        len(extracted.get("w", [])),
        bool(extracted.get("v")),
        bool(extracted.get("d")),
        bool(extracted.get("s")),
        len(extracted.get("pt", [])),
    )
    _record_audit(
        db,
        concert_id=concert.id,
        event_id=event.id,
        model=model_name,
        request_payload=request_payload,
        response_payload=response_payload or extracted,
        success=extraction_success,
        error_message=extraction_error,
    )

    matched_performers = 0
    matched_works = 0
    unresolved_count = 0

    # Venue handling is deterministic first. If unmatched, keep unresolved for manual review.
    venue_text = extracted["v"] or (concert.hall or "")
    if venue_text:
        venue_match = match_venue(db, venue_text)
        venue_match = _promote_ambiguous_match_if_possible("venue", venue_text, venue_match, config)
        logger.info(
            "entity_match_venue concert_id=%s status=%s confidence=%.3f normalized=%s candidate_count=%s",
            concert.id,
            venue_match.status,
            venue_match.confidence,
            venue_match.normalized_text,
            len(venue_match.candidates),
        )
        if venue_match.status == "matched" and venue_match.entity_id:
            event.venue_id = venue_match.entity_id
            add_venue_alias(db, venue_match.entity_id, venue_text)
            _queue_venue_merge_suggestions(db, venue_match.entity_id)
        else:
            triage_bucket, unresolved_status, review_priority = _triage_from_match_result(
                venue_match.status,
                venue_match.confidence,
            )
            event.venue_id = None
            unresolved_count += 1
            _create_unresolved(
                db,
                event_id=event.id,
                entity_type="venue",
                raw_text=venue_text,
                normalized_text=venue_match.normalized_text,
                candidates=venue_match.candidates,
                confidence_score=venue_match.confidence,
                triage_bucket=triage_bucket,
                status=unresolved_status,
                review_priority=review_priority,
            )

    if extracted["d"]:
        event.date = extracted["d"]

    event.sold_out = bool(extracted.get("s", False))
    event.price_tags = extracted.get("pt", []) if isinstance(extracted.get("pt"), list) else []

    for performer_name in extracted["p"]:
        performer_match = match_performer(db, performer_name)
        performer_match = _promote_ambiguous_match_if_possible("performer", performer_name, performer_match, config)
        logger.info(
            "entity_match_performer concert_id=%s performer=%s status=%s confidence=%.3f normalized=%s candidate_count=%s",
            concert.id,
            _preview_text(performer_name, limit=80),
            performer_match.status,
            performer_match.confidence,
            performer_match.normalized_text,
            len(performer_match.candidates),
        )
        if performer_match.status == "matched" and performer_match.entity_id:
            db.add(
                EventPerformer(
                    event_id=event.id,
                    performer_id=performer_match.entity_id,
                    role="performer",
                    confidence=performer_match.confidence,
                )
            )
            matched_performers += 1
            add_performer_alias(db, performer_match.entity_id, performer_name)
            _queue_performer_merge_suggestions(db, performer_match.entity_id)
            continue

        triage_bucket, unresolved_status, review_priority = _triage_from_match_result(
            performer_match.status,
            performer_match.confidence,
        )
        unresolved_count += 1
        _create_unresolved(
            db,
            event_id=event.id,
            entity_type="performer",
            raw_text=performer_name,
            normalized_text=performer_match.normalized_text,
            candidates=performer_match.candidates,
            confidence_score=performer_match.confidence,
            triage_bucket=triage_bucket,
            status=unresolved_status,
            review_priority=review_priority,
        )

    for order, work_payload in enumerate(extracted["w"], start=1):
        composer = work_payload.get("c", "")
        title = work_payload.get("t", "")
        normalized_work, work_match = match_work(db, composer, title)
        work_match = _promote_ambiguous_match_if_possible("work", f"{composer} {title}".strip(), work_match, config)
        logger.info(
            "entity_match_work concert_id=%s order=%s composer=%s title=%s status=%s confidence=%.3f normalized=%s candidate_count=%s",
            concert.id,
            order,
            _preview_text(composer, limit=70),
            _preview_text(title, limit=90),
            work_match.status,
            work_match.confidence,
            normalized_work.title_normalized,
            len(work_match.candidates),
        )
        if work_match.status == "matched" and work_match.entity_id:
            db.add(
                EventWork(
                    event_id=event.id,
                    work_id=work_match.entity_id,
                    sequence_order=order,
                    confidence=work_match.confidence,
                )
            )
            matched_works += 1
            continue

        raw_text = f"{composer} {title}".strip()
        triage_bucket, unresolved_status, review_priority = _triage_from_match_result(
            work_match.status,
            work_match.confidence,
        )
        unresolved_count += 1
        _create_unresolved(
            db,
            event_id=event.id,
            entity_type="work",
            raw_text=raw_text,
            normalized_text=work_match.normalized_text or pretty_label_for_unresolved("work", raw_text),
            candidates=work_match.candidates,
            confidence_score=work_match.confidence,
            triage_bucket=triage_bucket,
            status=unresolved_status,
            review_priority=review_priority,
        )

    db.add(event)
    db.flush()

    logger.info(
        "entity_pipeline_finished concert_id=%s event_id=%s matched_performers=%s matched_works=%s unresolved=%s",
        concert.id,
        event.id,
        matched_performers,
        matched_works,
        unresolved_count,
    )

    return PipelineResult(
        event_id=event.id,
        matched_performers=matched_performers,
        matched_works=matched_works,
        unresolved_count=unresolved_count,
    )


def resolve_unresolved_with_existing(db: Session, unresolved: UnresolvedEntity, selected_entity_id: int) -> None:
    event = db.get(Event, unresolved.event_id)
    if event is None:
        return

    if unresolved.entity_type == "performer":
        db.add(
            EventPerformer(
                event_id=event.id,
                performer_id=selected_entity_id,
                role="performer",
                confidence=0.9,
            )
        )
        add_performer_alias(db, selected_entity_id, unresolved.raw_text)
    elif unresolved.entity_type == "work":
        next_order = (
            db.scalar(
                select(EventWork.sequence_order)
                .where(EventWork.event_id == event.id)
                .order_by(EventWork.sequence_order.desc())
                .limit(1)
            )
            or 0
        )
        db.add(
            EventWork(
                event_id=event.id,
                work_id=selected_entity_id,
                sequence_order=next_order + 1,
                confidence=0.9,
            )
        )
    elif unresolved.entity_type == "venue":
        event.venue_id = selected_entity_id
        db.add(event)
        add_venue_alias(db, selected_entity_id, unresolved.raw_text)

    unresolved.status = "resolved"
    unresolved.resolution_action = "accept_candidate"
    unresolved.resolved_entity_id = selected_entity_id
    unresolved.triage_bucket = "safe"
    unresolved.review_priority = 9999
    db.add(unresolved)


def resolve_unresolved_with_new_entity(db: Session, unresolved: UnresolvedEntity, value: str) -> int | None:
    entity_id: int | None = None

    if unresolved.entity_type == "performer":
        created = create_performer(db, value)
        entity_id = created.id if created else None
    elif unresolved.entity_type == "venue":
        created = create_venue(db, value)
        entity_id = created.id if created else None
    elif unresolved.entity_type == "work":
        normalized_work, _ = match_work(db, "", value)
        created = create_work(db, normalized_work)
        entity_id = created.id if created else None

    if entity_id is None:
        return None

    resolve_unresolved_with_existing(db, unresolved, entity_id)
    unresolved.resolution_action = "create_new"
    db.add(unresolved)
    return entity_id


def mark_unresolved_distinct(db: Session, unresolved: UnresolvedEntity, candidate_id: int | None, reason: str) -> None:
    unresolved.status = "distinct"
    unresolved.resolution_action = "mark_distinct"
    db.add(unresolved)

    if candidate_id is None:
        return

    event = db.get(Event, unresolved.event_id)
    if event is None:
        return

    if unresolved.entity_type == "performer":
        linked_ids = db.scalars(
            select(EventPerformer.performer_id).where(EventPerformer.event_id == event.id)
        ).all()
    elif unresolved.entity_type == "work":
        linked_ids = db.scalars(select(EventWork.work_id).where(EventWork.event_id == event.id)).all()
    else:
        linked_ids = [event.venue_id] if event.venue_id else []

    for linked_id in linked_ids:
        if linked_id is None:
            continue
        entity_type, left_id, right_id = normalize_candidate_pair(unresolved.entity_type, linked_id, candidate_id)
        existing = db.scalar(
            select(DoNotMerge)
            .where(DoNotMerge.entity_type == entity_type)
            .where(DoNotMerge.entity_id_a == left_id)
            .where(DoNotMerge.entity_id_b == right_id)
            .limit(1)
        )
        if existing:
            continue
        db.add(
            DoNotMerge(
                entity_type=entity_type,
                entity_id_a=left_id,
                entity_id_b=right_id,
                reason=reason,
            )
        )


def _entity_label(db: Session, entity_type: str, entity_id: int) -> str:
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


def _remap_candidates(
    candidates: list[dict[str, Any]],
    keep_id: int,
    drop_id: int,
    keep_label: str,
) -> tuple[list[dict[str, Any]], bool]:
    changed = False
    deduped: dict[int, dict[str, Any]] = {}

    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        try:
            candidate_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        if candidate_id == drop_id:
            candidate_id = keep_id
            changed = True

        label = str(item.get("label", "") or "").strip()
        if candidate_id == keep_id and keep_label:
            label = keep_label

        try:
            score = float(item.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        candidate_payload = {
            "id": candidate_id,
            "label": label,
            "score": round(max(0.0, min(1.0, score)), 4),
        }

        existing = deduped.get(candidate_id)
        if existing is None or candidate_payload["score"] > float(existing.get("score", 0.0) or 0.0):
            deduped[candidate_id] = candidate_payload

    ordered = sorted(deduped.values(), key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
    return ordered, changed


def _remap_open_candidates_after_merge(
    db: Session,
    entity_type: str,
    keep_id: int,
    drop_id: int,
) -> None:
    keep_label = _entity_label(db, entity_type, keep_id)

    unresolved_rows = db.scalars(select(UnresolvedEntity).where(UnresolvedEntity.entity_type == entity_type)).all()
    for unresolved in unresolved_rows:
        remapped, changed = _remap_candidates(unresolved.candidates_json or [], keep_id, drop_id, keep_label)
        if changed:
            unresolved.candidates_json = remapped
            if unresolved.resolved_entity_id == drop_id:
                unresolved.resolved_entity_id = keep_id
            db.add(unresolved)

    suggestion_rows = db.scalars(select(MatchSuggestion).where(MatchSuggestion.entity_type == entity_type)).all()
    for suggestion in suggestion_rows:
        remapped, changed = _remap_candidates(suggestion.candidates_json or [], keep_id, drop_id, keep_label)
        if changed:
            suggestion.candidates_json = remapped
            if suggestion.selected_candidate_id == drop_id:
                suggestion.selected_candidate_id = keep_id
            db.add(suggestion)


def _merge_performers(db: Session, keep_id: int, drop_id: int) -> bool:
    keep = db.get(Performer, keep_id)
    drop = db.get(Performer, drop_id)
    if keep is None or drop is None:
        return False

    drop_links = db.scalars(select(EventPerformer).where(EventPerformer.performer_id == drop_id)).all()
    for link in drop_links:
        existing = db.scalar(
            select(EventPerformer)
            .where(EventPerformer.event_id == link.event_id)
            .where(EventPerformer.performer_id == keep_id)
            .where(EventPerformer.role == link.role)
            .limit(1)
        )
        if existing:
            existing.confidence = max(float(existing.confidence or 0.0), float(link.confidence or 0.0))
            db.add(existing)
            db.delete(link)
        else:
            link.performer_id = keep_id
            db.add(link)

    drop_aliases = db.scalars(select(PerformerAlias).where(PerformerAlias.performer_id == drop_id)).all()
    for alias in drop_aliases:
        existing_alias = db.scalar(
            select(PerformerAlias)
            .where(PerformerAlias.performer_id == keep_id)
            .where(PerformerAlias.normalized == alias.normalized)
            .limit(1)
        )
        if existing_alias:
            db.delete(alias)
        else:
            alias.performer_id = keep_id
            db.add(alias)

    if not (keep.native_name or "").strip() and (drop.native_name or "").strip():
        keep.native_name = drop.native_name
    db.add(keep)
    db.delete(drop)
    db.flush()
    return True


def _merge_venues(db: Session, keep_id: int, drop_id: int) -> bool:
    keep = db.get(Venue, keep_id)
    drop = db.get(Venue, drop_id)
    if keep is None or drop is None:
        return False

    linked_events = db.scalars(select(Event).where(Event.venue_id == drop_id)).all()
    for event in linked_events:
        event.venue_id = keep_id
        db.add(event)

    drop_aliases = db.scalars(select(VenueAlias).where(VenueAlias.venue_id == drop_id)).all()
    for alias in drop_aliases:
        existing_alias = db.scalar(
            select(VenueAlias)
            .where(VenueAlias.venue_id == keep_id)
            .where(VenueAlias.normalized == alias.normalized)
            .limit(1)
        )
        if existing_alias:
            db.delete(alias)
        else:
            alias.venue_id = keep_id
            db.add(alias)

    db.delete(drop)
    db.flush()
    return True


def _merge_works(db: Session, keep_id: int, drop_id: int) -> bool:
    keep = db.get(Work, keep_id)
    drop = db.get(Work, drop_id)
    if keep is None or drop is None:
        return False

    drop_links = db.scalars(select(EventWork).where(EventWork.work_id == drop_id)).all()
    for link in drop_links:
        existing = db.scalar(
            select(EventWork)
            .where(EventWork.event_id == link.event_id)
            .where(EventWork.work_id == keep_id)
            .where(EventWork.sequence_order == link.sequence_order)
            .limit(1)
        )
        if existing:
            existing.confidence = max(float(existing.confidence or 0.0), float(link.confidence or 0.0))
            db.add(existing)
            db.delete(link)
        else:
            link.work_id = keep_id
            db.add(link)

    db.delete(drop)
    db.flush()
    return True


def merge_entities(
    db: Session,
    entity_type: str,
    candidate_a_id: int,
    candidate_b_id: int,
) -> tuple[int, int] | None:
    entity_type, keep_id, drop_id = normalize_candidate_pair(entity_type, candidate_a_id, candidate_b_id)
    if keep_id == drop_id:
        return None

    if entity_type == "performer":
        merged = _merge_performers(db, keep_id, drop_id)
    elif entity_type == "venue":
        merged = _merge_venues(db, keep_id, drop_id)
    elif entity_type == "work":
        merged = _merge_works(db, keep_id, drop_id)
    else:
        return None

    if not merged:
        return None

    _remap_open_candidates_after_merge(db, entity_type, keep_id, drop_id)
    return keep_id, drop_id
