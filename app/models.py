from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Concert(Base):
    __tablename__ = "concerts"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(128), nullable=False)
    source_url = Column(String(512), nullable=False)
    external_id = Column(String(256), nullable=False, index=True)
    name = Column(String(512), nullable=False, index=True)
    program = Column(Text, nullable=True)
    performers = Column(Text, nullable=True)
    hall = Column(Text, nullable=True)
    date = Column(String(64), nullable=True, index=True)
    date_normalized = Column(String(16), nullable=True, index=True)
    time = Column(String(64), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class Performer(Base):
    __tablename__ = "performers"

    id = Column(Integer, primary_key=True, index=True)
    canonical_name = Column(String(256), nullable=False)
    canonical_normalized = Column(String(256), nullable=False, index=True, unique=True)
    native_name = Column(String(256), nullable=True, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    aliases = relationship("PerformerAlias", back_populates="performer", cascade="all, delete-orphan")


class PerformerAlias(Base):
    __tablename__ = "performer_aliases"
    __table_args__ = (UniqueConstraint("performer_id", "normalized", name="uq_performer_alias_norm"),)

    id = Column(Integer, primary_key=True, index=True)
    performer_id = Column(Integer, ForeignKey("performers.id"), nullable=False, index=True)
    alias = Column(String(256), nullable=False)
    script = Column(String(32), nullable=False, default="unknown")
    normalized = Column(String(256), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    performer = relationship("Performer", back_populates="aliases")


class Work(Base):
    __tablename__ = "works"

    id = Column(Integer, primary_key=True, index=True)
    composer = Column(String(256), nullable=False, default="")
    composer_normalized = Column(String(256), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    title_normalized = Column(String(512), nullable=False, index=True)
    form = Column(String(64), nullable=False, default="")
    number = Column(Integer, nullable=True)
    opus = Column(String(64), nullable=False, default="")
    key = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    name_normalized = Column(String(256), nullable=False, index=True, unique=True)
    city = Column(String(128), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    aliases = relationship("VenueAlias", back_populates="venue", cascade="all, delete-orphan")


class VenueAlias(Base):
    __tablename__ = "venue_aliases"
    __table_args__ = (UniqueConstraint("venue_id", "normalized", name="uq_venue_alias_norm"),)

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    alias = Column(String(256), nullable=False)
    normalized = Column(String(256), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    venue = relationship("Venue", back_populates="aliases")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    concert_id = Column(Integer, ForeignKey("concerts.id"), nullable=False, unique=True, index=True)
    title = Column(String(512), nullable=False)
    date = Column(String(16), nullable=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=True, index=True)
    sold_out = Column(Boolean, nullable=False, default=False)
    price_tags = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventPerformer(Base):
    __tablename__ = "event_performers"
    __table_args__ = (UniqueConstraint("event_id", "performer_id", "role", name="uq_event_performer"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    performer_id = Column(Integer, ForeignKey("performers.id"), nullable=False, index=True)
    role = Column(String(64), nullable=False, default="performer")
    confidence = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventWork(Base):
    __tablename__ = "event_works"
    __table_args__ = (UniqueConstraint("event_id", "work_id", "sequence_order", name="uq_event_work"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    work_id = Column(Integer, ForeignKey("works.id"), nullable=False, index=True)
    sequence_order = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class UnresolvedEntity(Base):
    __tablename__ = "unresolved_entities"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False, index=True)
    raw_text = Column(String(512), nullable=False)
    normalized_text = Column(String(512), nullable=False, default="")
    candidates_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="open", index=True)
    triage_bucket = Column(String(16), nullable=False, default="critical", index=True)
    confidence_score = Column(Float, nullable=False, default=0.0, index=True)
    review_priority = Column(Integer, nullable=False, default=1000, index=True)
    resolved_entity_id = Column(Integer, nullable=True)
    resolution_action = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class MatchSuggestion(Base):
    __tablename__ = "match_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    unresolved_entity_id = Column(Integer, ForeignKey("unresolved_entities.id"), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False, index=True)
    input_text = Column(String(512), nullable=False)
    candidates_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="pending", index=True)
    selected_candidate_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class MergeSuggestion(Base):
    __tablename__ = "merge_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(32), nullable=False, index=True)
    candidate_a_id = Column(Integer, nullable=False)
    candidate_b_id = Column(Integer, nullable=False)
    score = Column(Float, nullable=False, default=0.0)
    llm_assessment = Column(String(64), nullable=False, default="")
    confidence = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=False, default="")
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)


class DoNotMerge(Base):
    __tablename__ = "do_not_merge"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id_a", "entity_id_b", name="uq_do_not_merge_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(32), nullable=False, index=True)
    entity_id_a = Column(Integer, nullable=False)
    entity_id_b = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtractionAudit(Base):
    __tablename__ = "extraction_audits"

    id = Column(Integer, primary_key=True, index=True)
    concert_id = Column(Integer, ForeignKey("concerts.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True, index=True)
    provider = Column(String(64), nullable=False, default="openrouter")
    model = Column(String(128), nullable=False, default="")
    request_payload = Column(JSON, nullable=False, default=dict)
    response_payload = Column(JSON, nullable=False, default=dict)
    success = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    scrape_interval_minutes = Column(Integer, default=60)
    smtp_host = Column(String(256), default="")
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String(256), default="")
    smtp_password = Column(String(256), default="")
    sender_email = Column(String(256), default="")
    recipient_email = Column(String(256), default="")
    notifications_enabled = Column(Boolean, default=False)
    openrouter_api_key = Column(String(512), default="")
    openrouter_model = Column(String(128), default="openai/gpt-4.1-mini")
    openrouter_timeout_seconds = Column(Integer, default=40)
    openrouter_max_retries = Column(Integer, default=2)


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name_contains = Column(String(256), default="")
    performer_contains = Column(String(256), default="")
    program_contains = Column(String(256), default="")
    date_contains = Column(String(64), default="")
    time_contains = Column(String(64), default="")
    enabled = Column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(256), nullable=False, unique=True, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="contributor", index=True)
    trust_level = Column(String(32), nullable=False, default="new", index=True)
    notifications_enabled = Column(Boolean, nullable=False, default=False)
    notification_email = Column(String(256), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
