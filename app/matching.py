from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Performer, PerformerAlias, Venue, VenueAlias, Work
from .normalization import WorkNormalized, normalize_text, normalize_venue, normalize_work, performer_variants


HIGH_CONFIDENCE_THRESHOLD = 0.95
AMBIGUOUS_THRESHOLD = 0.85
MAX_CANDIDATES = 5


@dataclass
class MatchResult:
    status: str
    entity_id: int | None
    confidence: float
    normalized_text: str
    candidates: list[dict[str, Any]]


def _score_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    sequence_ratio = SequenceMatcher(None, left, right).ratio()
    trigram_ratio = _trigram_jaccard(left, right)
    token_ratio = _token_jaccard(left, right)
    return (sequence_ratio * 0.5) + (trigram_ratio * 0.35) + (token_ratio * 0.15)


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if token}
    right_tokens = {token for token in right.split() if token}
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / max(len(union), 1)


def _trigrams(value: str) -> set[str]:
    padded = f"  {value} "
    if len(padded) < 3:
        return {padded}
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def _trigram_jaccard(left: str, right: str) -> float:
    left_grams = _trigrams(left)
    right_grams = _trigrams(right)
    if not left_grams and not right_grams:
        return 1.0
    if not left_grams or not right_grams:
        return 0.0
    intersection = left_grams & right_grams
    union = left_grams | right_grams
    return len(intersection) / max(len(union), 1)


def _optional_text_score(left: str, right: str) -> float:
    left_clean = normalize_text(left)
    right_clean = normalize_text(right)

    if not left_clean and not right_clean:
        return 0.5
    if not left_clean or not right_clean:
        return 0.35
    if left_clean == right_clean:
        return 1.0
    if left_clean in right_clean or right_clean in left_clean:
        return 0.8
    return _score_similarity(left_clean, right_clean)


def _optional_number_score(left: int | None, right: int | None) -> float:
    if left is None and right is None:
        return 0.5
    if left is None or right is None:
        return 0.35
    return 1.0 if left == right else 0.0


def _build_candidate(entity_id: int, label: str, score: float) -> dict[str, Any]:
    return {
        "id": entity_id,
        "label": label,
        "score": round(score, 4),
    }


def match_performer(db: Session, raw_name: str) -> MatchResult:
    normalized, variants, script = performer_variants(raw_name)
    if not normalized:
        return MatchResult(status="unresolved", entity_id=None, confidence=0.0, normalized_text="", candidates=[])

    alias = db.scalar(select(PerformerAlias).where(PerformerAlias.normalized.in_(variants)).limit(1))
    if alias:
        return MatchResult(
            status="matched",
            entity_id=alias.performer_id,
            confidence=1.0,
            normalized_text=normalized,
            candidates=[_build_candidate(alias.performer_id, alias.alias, 1.0)],
        )

    canonical = db.scalar(select(Performer).where(Performer.canonical_normalized.in_(variants)).limit(1))
    if canonical:
        return MatchResult(
            status="matched",
            entity_id=canonical.id,
            confidence=1.0,
            normalized_text=normalized,
            candidates=[_build_candidate(canonical.id, canonical.canonical_name, 1.0)],
        )

    candidates: list[dict[str, Any]] = []
    performer_rows = db.scalars(select(Performer).limit(1000)).all()
    for performer in performer_rows:
        score = max(_score_similarity(variant, performer.canonical_normalized) for variant in variants)
        candidates.append(_build_candidate(performer.id, performer.canonical_name, score))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    candidates = candidates[:MAX_CANDIDATES]
    top_score = candidates[0]["score"] if candidates else 0.0

    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        return MatchResult(
            status="matched",
            entity_id=int(candidates[0]["id"]),
            confidence=top_score,
            normalized_text=normalized,
            candidates=candidates,
        )

    if top_score >= AMBIGUOUS_THRESHOLD:
        return MatchResult(
            status="ambiguous",
            entity_id=None,
            confidence=top_score,
            normalized_text=normalized,
            candidates=candidates,
        )

    return MatchResult(
        status="unresolved",
        entity_id=None,
        confidence=top_score,
        normalized_text=normalized,
        candidates=candidates,
    )


def create_performer(db: Session, raw_name: str) -> Performer | None:
    normalized, variants, script = performer_variants(raw_name)
    if not normalized:
        return None

    existing = db.scalar(select(Performer).where(Performer.canonical_normalized == normalized).limit(1))
    if existing:
        return existing

    performer = Performer(canonical_name=raw_name.strip(), canonical_normalized=normalized, native_name=raw_name.strip())
    db.add(performer)
    db.flush()

    for variant in variants:
        alias = PerformerAlias(
            performer_id=performer.id,
            alias=raw_name.strip(),
            normalized=variant,
            script=script,
        )
        db.add(alias)

    db.flush()
    return performer


def add_performer_alias(db: Session, performer_id: int, alias_text: str) -> None:
    alias_clean = str(alias_text or "").strip()
    if not alias_clean:
        return

    _, variants, script = performer_variants(alias_clean)
    for variant in variants:
        if not variant:
            continue
        exists = db.scalar(
            select(PerformerAlias)
            .where(PerformerAlias.performer_id == performer_id)
            .where(PerformerAlias.normalized == variant)
            .limit(1)
        )
        if exists:
            continue
        db.add(
            PerformerAlias(
                performer_id=performer_id,
                alias=alias_clean,
                normalized=variant,
                script=script,
            )
        )

    db.flush()


def match_venue(db: Session, raw_name: str) -> MatchResult:
    normalized = normalize_venue(raw_name)
    if not normalized:
        return MatchResult(status="unresolved", entity_id=None, confidence=0.0, normalized_text="", candidates=[])

    alias = db.scalar(select(VenueAlias).where(VenueAlias.normalized == normalized).limit(1))
    if alias:
        return MatchResult(
            status="matched",
            entity_id=alias.venue_id,
            confidence=1.0,
            normalized_text=normalized,
            candidates=[_build_candidate(alias.venue_id, alias.alias, 1.0)],
        )

    canonical = db.scalar(select(Venue).where(Venue.name_normalized == normalized).limit(1))
    if canonical:
        return MatchResult(
            status="matched",
            entity_id=canonical.id,
            confidence=1.0,
            normalized_text=normalized,
            candidates=[_build_candidate(canonical.id, canonical.name, 1.0)],
        )

    candidates: list[dict[str, Any]] = []
    venue_rows = db.scalars(select(Venue).limit(1000)).all()
    for venue in venue_rows:
        score = _score_similarity(normalized, venue.name_normalized)
        candidates.append(_build_candidate(venue.id, venue.name, score))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    candidates = candidates[:MAX_CANDIDATES]
    top_score = candidates[0]["score"] if candidates else 0.0

    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        return MatchResult(
            status="matched",
            entity_id=int(candidates[0]["id"]),
            confidence=top_score,
            normalized_text=normalized,
            candidates=candidates,
        )

    if top_score >= AMBIGUOUS_THRESHOLD:
        return MatchResult(
            status="ambiguous",
            entity_id=None,
            confidence=top_score,
            normalized_text=normalized,
            candidates=candidates,
        )

    return MatchResult(
        status="unresolved",
        entity_id=None,
        confidence=top_score,
        normalized_text=normalized,
        candidates=candidates,
    )


def create_venue(db: Session, raw_name: str) -> Venue | None:
    normalized = normalize_venue(raw_name)
    if not normalized:
        return None

    existing = db.scalar(select(Venue).where(Venue.name_normalized == normalized).limit(1))
    if existing:
        return existing

    venue = Venue(name=raw_name.strip(), name_normalized=normalized)
    db.add(venue)
    db.flush()

    db.add(VenueAlias(venue_id=venue.id, alias=raw_name.strip(), normalized=normalized))
    db.flush()
    return venue


def add_venue_alias(db: Session, venue_id: int, alias_text: str) -> None:
    alias_clean = str(alias_text or "").strip()
    if not alias_clean:
        return

    normalized = normalize_venue(alias_clean)
    if not normalized:
        return

    exists = db.scalar(
        select(VenueAlias)
        .where(VenueAlias.venue_id == venue_id)
        .where(VenueAlias.normalized == normalized)
        .limit(1)
    )
    if exists:
        return

    db.add(VenueAlias(venue_id=venue_id, alias=alias_clean, normalized=normalized))
    db.flush()


def match_work(db: Session, composer: str, title: str) -> tuple[WorkNormalized, MatchResult]:
    normalized = normalize_work(composer, title)
    if not normalized.title_normalized:
        return normalized, MatchResult(status="unresolved", entity_id=None, confidence=0.0, normalized_text="", candidates=[])

    exact = db.scalar(
        select(Work)
        .where(Work.title_normalized == normalized.title_normalized)
        .where(Work.composer_normalized == normalized.composer_normalized)
        .limit(1)
    )
    if exact:
        return normalized, MatchResult(
            status="matched",
            entity_id=exact.id,
            confidence=1.0,
            normalized_text=normalized.title_normalized,
            candidates=[_build_candidate(exact.id, exact.title, 1.0)],
        )

    candidates: list[dict[str, Any]] = []
    work_rows = db.scalars(select(Work).limit(2000)).all()
    for work in work_rows:
        title_score = _score_similarity(normalized.title_normalized, work.title_normalized)
        composer_score = _score_similarity(normalized.composer_normalized, work.composer_normalized)
        form_score = _optional_text_score(normalized.form, work.form)
        number_score = _optional_number_score(normalized.number, work.number)
        opus_score = _optional_text_score(normalized.opus, work.opus)
        key_score = _optional_text_score(normalized.key, work.key)
        score = (
            (title_score * 0.35)
            + (composer_score * 0.25)
            + (form_score * 0.15)
            + (number_score * 0.1)
            + (opus_score * 0.1)
            + (key_score * 0.05)
        )
        candidates.append(_build_candidate(work.id, f"{work.composer} - {work.title}", score))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    candidates = candidates[:MAX_CANDIDATES]
    top_score = candidates[0]["score"] if candidates else 0.0

    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        return normalized, MatchResult(
            status="matched",
            entity_id=int(candidates[0]["id"]),
            confidence=top_score,
            normalized_text=normalized.title_normalized,
            candidates=candidates,
        )

    if top_score >= AMBIGUOUS_THRESHOLD:
        return normalized, MatchResult(
            status="ambiguous",
            entity_id=None,
            confidence=top_score,
            normalized_text=normalized.title_normalized,
            candidates=candidates,
        )

    return normalized, MatchResult(
        status="unresolved",
        entity_id=None,
        confidence=top_score,
        normalized_text=normalized.title_normalized,
        candidates=candidates,
    )


def create_work(db: Session, normalized: WorkNormalized) -> Work | None:
    if not normalized.title_normalized:
        return None

    existing = db.scalar(
        select(Work)
        .where(Work.title_normalized == normalized.title_normalized)
        .where(Work.composer_normalized == normalized.composer_normalized)
        .limit(1)
    )
    if existing:
        return existing

    work = Work(
        composer=normalized.composer,
        composer_normalized=normalized.composer_normalized,
        title=normalized.title,
        title_normalized=normalized.title_normalized,
        form=normalized.form,
        number=normalized.number,
        opus=normalized.opus,
        key=normalized.key,
    )
    db.add(work)
    db.flush()
    return work


def normalize_candidate_pair(entity_type: str, left_id: int, right_id: int) -> tuple[str, int, int]:
    if left_id <= right_id:
        return entity_type, left_id, right_id
    return entity_type, right_id, left_id


def pretty_label_for_unresolved(entity_type: str, raw_text: str) -> str:
    return normalize_text(raw_text) if entity_type != "venue" else normalize_venue(raw_text)
