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


class RuleCreate(BaseModel):
    name_contains: str = ""
    performer_contains: str = ""
    program_contains: str = ""
    date_contains: str = ""
    time_contains: str = ""
    enabled: bool = True
