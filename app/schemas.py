from typing import Literal

from pydantic import BaseModel, EmailStr


class SettingsUpdate(BaseModel):
    scrape_interval_minutes: int
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    sender_email: EmailStr | None = None
    recipient_email: EmailStr | None = None
    notifications_enabled: bool = False
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"
    openrouter_timeout_seconds: int = 40
    openrouter_max_retries: int = 2


class RuleCreate(BaseModel):
    name_contains: str = ""
    performer_contains: str = ""
    program_contains: str = ""
    date_contains: str = ""
    time_contains: str = ""
    enabled: bool = True


class ScrapeNowRequest(BaseModel):
    sources: list[str] = []
    max_per_source: int | None = None
    max_total: int | None = None


class ResolveUnresolvedRequest(BaseModel):
    action: Literal["accept_candidate", "create_new", "mark_distinct", "reject", "skip"]
    candidate_id: int | None = None
    value: str = ""
    reason: str = ""
    apply_globally: bool = False


class UpdateMergeSuggestionRequest(BaseModel):
    action: Literal["merge", "reject", "do_not_merge"]
    reason: str = ""


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class NotificationProfileUpdate(BaseModel):
    notifications_enabled: bool = False
    notification_email: EmailStr | None = None
