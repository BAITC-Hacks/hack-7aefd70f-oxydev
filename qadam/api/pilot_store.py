"""Локальное хранилище добровольных пилотных прохождений.

Это не production-СRM: кандидат представлен случайным кодом, а удаление,
срок хранения и роли должны быть согласованы до работы с реальными данными.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "demo" / "pilot.sqlite3"
DEFAULT_MEDIA = Path(__file__).resolve().parent.parent / "data" / "demo" / "media"


def database_path() -> Path:
    return Path(os.environ.get("QADAM_PILOT_DB", str(DEFAULT_DB)))


def media_directory() -> Path:
    return Path(os.environ.get("QADAM_PILOT_MEDIA", str(DEFAULT_MEDIA)))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS pilot_submissions (
            id TEXT PRIMARY KEY,
            language TEXT NOT NULL,
            mode TEXT NOT NULL,
            story TEXT NOT NULL,
            media_link TEXT,
            media_content_type TEXT,
            scenario_choice TEXT NOT NULL,
            rationale TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS pilot_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL REFERENCES pilot_submissions(id),
            reviewer TEXT NOT NULL,
            selected_route TEXT NOT NULL,
            reason TEXT NOT NULL,
            evidence TEXT NOT NULL,
            timecode TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
    """)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_submission(**fields: str | None) -> dict:
    submission_id = "QDM-" + secrets.token_hex(4).upper()
    with connect() as db:
        db.execute("""
            INSERT INTO pilot_submissions
              (id, language, mode, story, media_link, scenario_choice,
               rationale, consent_version)
            VALUES (:id, :language, :mode, :story, :media_link,
                    :scenario_choice, :rationale, :consent_version)
        """, {"id": submission_id, **fields})
        return dict(db.execute(
            "SELECT * FROM pilot_submissions WHERE id=?", (submission_id,)
        ).fetchone())


def submissions() -> list[dict]:
    with connect() as db:
        rows = db.execute("""
            SELECT s.*,
              (SELECT selected_route FROM pilot_reviews r
               WHERE r.submission_id=s.id ORDER BY r.id DESC LIMIT 1) latest_route
            FROM pilot_submissions s ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(row) for row in rows]


def submission(submission_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM pilot_submissions WHERE id=?", (submission_id,)
        ).fetchone()
        return dict(row) if row else None


def set_media(submission_id: str, content_type: str) -> None:
    with connect() as db:
        db.execute("UPDATE pilot_submissions SET media_content_type=? WHERE id=?",
                   (content_type, submission_id))


def append_review(**fields: str) -> dict:
    with connect() as db:
        cursor = db.execute("""
            INSERT INTO pilot_reviews
              (submission_id, reviewer, selected_route, reason, evidence, timecode)
            VALUES (:submission_id, :reviewer, :selected_route, :reason,
                    :evidence, :timecode)
        """, fields)
        return dict(db.execute(
            "SELECT * FROM pilot_reviews WHERE id=?", (cursor.lastrowid,)
        ).fetchone())


def reviews(submission_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute("""
            SELECT * FROM pilot_reviews WHERE submission_id=?
            ORDER BY id DESC LIMIT 100
        """, (submission_id,)).fetchall()
        return [dict(row) for row in rows]


def delete_submission(submission_id: str) -> bool:
    """Удалить одно прохождение и его журнал; вызывается только по точному ID."""
    with connect() as db:
        db.execute("DELETE FROM pilot_reviews WHERE submission_id=?", (submission_id,))
        cursor = db.execute("DELETE FROM pilot_submissions WHERE id=?", (submission_id,))
        return cursor.rowcount == 1
