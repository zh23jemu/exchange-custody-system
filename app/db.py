from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_URL = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def build_engine(database_url: str | None = None):
    ensure_data_dir()
    return create_engine(
        database_url or get_database_url(),
        connect_args={"check_same_thread": False},
        future=True,
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
