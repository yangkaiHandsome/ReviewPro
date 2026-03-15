from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
    future=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def _migrate_sqlite_rules_primary_key() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='rules'")
        ).fetchone()
        if row is None or row[0] is None:
            return

        create_sql = row[0]
        if "PRIMARY KEY (id, strategy_id)" in create_sql:
            return

        if "PRIMARY KEY (id)" not in create_sql:
            return

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("ALTER TABLE rules RENAME TO rules_legacy"))
        connection.execute(
            text(
                """
                CREATE TABLE rules (
                    id VARCHAR(64) NOT NULL,
                    strategy_id VARCHAR(36) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL,
                    severity VARCHAR(16) NOT NULL,
                    is_required BOOLEAN NOT NULL,
                    PRIMARY KEY (id, strategy_id),
                    FOREIGN KEY(strategy_id) REFERENCES strategies (id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO rules (id, strategy_id, title, description, severity, is_required)
                SELECT id, strategy_id, title, description, severity, is_required
                FROM rules_legacy
                """
            )
        )
        connection.execute(text("DROP TABLE rules_legacy"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_rules_strategy_id ON rules (strategy_id)"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_rules_primary_key()


