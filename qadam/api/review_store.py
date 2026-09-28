"""Журнал учебного workflow: только ID вымышленных примеров и действия.

Не является хранилищем заявок кандидатов или production audit trail.
Исходные тексты и цитаты здесь никогда не записываются.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "demo" / "reviews.sqlite3"


def database_path() -> Path:
    return Path(os.environ.get("QADAM_DEMO_DB", str(DEFAULT_DB)))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""
        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            example_id TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            model_route TEXT NOT NULL,
            selected_route TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            model_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
    """)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def append_event(**fields: str) -> dict:
    with connect() as db:
        cursor = db.execute("""
            INSERT INTO review_events
              (example_id, reviewer, model_route, selected_route, action,
               reason, model_version)
            VALUES (:example_id, :reviewer, :model_route, :selected_route,
                    :action, :reason, :model_version)
        """, fields)
        row = db.execute(
            "SELECT * FROM review_events WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def events(example_id: str, limit: int = 50) -> list[dict]:
    with connect() as db:
        rows = db.execute("""
            SELECT * FROM review_events WHERE example_id=?
            ORDER BY id DESC LIMIT ?
        """, (example_id, limit)).fetchall()
        return [dict(row) for row in rows]
