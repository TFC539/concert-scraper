from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./concerts.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    inspector = inspect(engine)
    if "concerts" not in inspector.get_table_names():
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

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
