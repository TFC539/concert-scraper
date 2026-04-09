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

    if "unresolved_entities" in table_names:
        unresolved_columns = {column["name"] for column in inspector.get_columns("unresolved_entities")}
        unresolved_indexes = {index["name"] for index in inspector.get_indexes("unresolved_entities")}
        if "triage_bucket" not in unresolved_columns:
            statements.append("ALTER TABLE unresolved_entities ADD COLUMN triage_bucket VARCHAR(16) DEFAULT 'critical'")
        if "confidence_score" not in unresolved_columns:
            statements.append("ALTER TABLE unresolved_entities ADD COLUMN confidence_score FLOAT DEFAULT 0.0")
        if "review_priority" not in unresolved_columns:
            statements.append("ALTER TABLE unresolved_entities ADD COLUMN review_priority INTEGER DEFAULT 1000")
        if "ix_unresolved_entities_triage_bucket" not in unresolved_indexes:
            statements.append("CREATE INDEX ix_unresolved_entities_triage_bucket ON unresolved_entities (triage_bucket)")
        if "ix_unresolved_entities_confidence_score" not in unresolved_indexes:
            statements.append("CREATE INDEX ix_unresolved_entities_confidence_score ON unresolved_entities (confidence_score)")
        if "ix_unresolved_entities_review_priority" not in unresolved_indexes:
            statements.append("CREATE INDEX ix_unresolved_entities_review_priority ON unresolved_entities (review_priority)")

    if "users" in table_names:
        users_columns = {column["name"] for column in inspector.get_columns("users")}
        users_indexes = {index["name"] for index in inspector.get_indexes("users")}
        if "role" not in users_columns:
            statements.append("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'contributor'")
        if "notifications_enabled" not in users_columns:
            statements.append("ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 0")
        if "notification_email" not in users_columns:
            statements.append("ALTER TABLE users ADD COLUMN notification_email VARCHAR(256) DEFAULT ''")
        if "ix_users_role" not in users_indexes:
            statements.append("CREATE INDEX ix_users_role ON users (role)")
        statements.append(
            "UPDATE users SET role = 'admin' "
            "WHERE id = (SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1) "
            "AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin')"
        )

    if "notification_rules" in table_names:
        notification_rule_columns = {column["name"] for column in inspector.get_columns("notification_rules")}
        notification_rule_indexes = {index["name"] for index in inspector.get_indexes("notification_rules")}
        if "user_id" not in notification_rule_columns:
            statements.append("ALTER TABLE notification_rules ADD COLUMN user_id INTEGER")
        if "ix_notification_rules_user_id" not in notification_rule_indexes:
            statements.append("CREATE INDEX ix_notification_rules_user_id ON notification_rules (user_id)")
        statements.append(
            "UPDATE notification_rules SET user_id = "
            "(SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1) "
            "WHERE user_id IS NULL"
        )

    if not statements:
        logger.info("ensure_schema_no_changes")
        return

    logger.info("ensure_schema_apply statements=%s", len(statements))
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    logger.info("ensure_schema_complete")
