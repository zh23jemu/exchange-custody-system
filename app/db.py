from __future__ import annotations

import os
import sqlite3
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


def get_sqlite_db_path() -> Path | None:
    database_url = get_database_url()
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.replace("sqlite:///", "", 1))


def detect_schema_warnings() -> list[str]:
    db_path = get_sqlite_db_path()
    if db_path is None or not db_path.exists():
        return []

    warnings: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(orders)").fetchall()
    finally:
        conn.close()

    if rows:
        orders_columns = {row[1]: row for row in rows}
        needs_migration = []
        for column_name in ("target_account_id", "payout_amount", "payout_currency"):
            column = orders_columns.get(column_name)
            if column and column[3] == 1:
                needs_migration.append(column_name)
        if needs_migration:
            warnings.append(
                "当前数据库仍是旧结构："
                + ", ".join(f"orders.{item}" for item in needs_migration)
                + " 仍为必填。请先运行迁移脚本 scripts/migrate_orders_target_account_nullable.py。"
            )
    return warnings
