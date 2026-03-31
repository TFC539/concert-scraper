from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

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
    date = Column(String(64), nullable=True, index=True)
    time = Column(String(64), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


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


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id = Column(Integer, primary_key=True, index=True)
    name_contains = Column(String(256), default="")
    performer_contains = Column(String(256), default="")
    program_contains = Column(String(256), default="")
    date_contains = Column(String(64), default="")
    time_contains = Column(String(64), default="")
    enabled = Column(Boolean, default=True)
