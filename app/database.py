import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./concerts.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "concerts" not in table_names:
        logger.info("ensure_schema_skipped concerts_table_missing")
        return

    columns = {column["name"] for column in inspector.get_columns("concerts")}
    indexes = {index["name"] for index in inspector.get_indexes("concerts")}

    statements: list[str] = []
    if "hall" not in columns:
        statements.append("ALTER TABLE concerts ADD COLUMN hall TEXT")
    if "date_normalized" not in columns:
        statements.append("ALTER TABLE concerts ADD COLUMN date_normalized VARCHAR(16)")
    if "ix_concerts_date_normalized" not in indexes:
        statements.append("CREATE INDEX ix_concerts_date_normalized ON concerts (date_normalized)")

    if "app_settings" in table_names:
        app_settings_columns = {column["name"] for column in inspector.get_columns("app_settings")}
        if "openrouter_api_key" not in app_settings_columns:
            statements.append("ALTER TABLE app_settings ADD COLUMN openrouter_api_key VARCHAR(512) DEFAULT ''")
        if "openrouter_model" not in app_settings_columns:
            statements.append(
                "ALTER TABLE app_settings ADD COLUMN openrouter_model VARCHAR(128) DEFAULT 'openai/gpt-4.1-mini'"
            )
        if "openrouter_timeout_seconds" not in app_settings_columns:
            statements.append("ALTER TABLE app_settings ADD COLUMN openrouter_timeout_seconds INTEGER DEFAULT 40")
        if "openrouter_max_retries" not in app_settings_columns:
            statements.append("ALTER TABLE app_settings ADD COLUMN openrouter_max_retries INTEGER DEFAULT 2")

    if "events" in table_names:
        events_columns = {column["name"] for column in inspector.get_columns("events")}
        if "sold_out" not in events_columns:
            statements.append("ALTER TABLE events ADD COLUMN sold_out BOOLEAN DEFAULT 0")
        if "price_tags" not in events_columns:
            statements.append("ALTER TABLE events ADD COLUMN price_tags JSON DEFAULT '[]'")

    if not statements:
        logger.info("ensure_schema_no_changes")
        return

    logger.info("ensure_schema_apply statements=%s", len(statements))
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    logger.info("ensure_schema_complete")
