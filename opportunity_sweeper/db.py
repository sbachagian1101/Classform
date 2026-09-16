from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "opportunities.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    published_date TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    match_score REAL NOT NULL,
    matched_personas TEXT,
    matched_keywords TEXT
);
"""


def opportunity_id(url: str) -> str:
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()


@dataclass
class Opportunity:
    title: str
    url: str
    source: str
    category: str
    description: str = ""
    published_date: str = ""
    match_score: float = 0.0
    matched_personas: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, opp: Opportunity) -> bool:
    """Insert or update an opportunity. Returns True if it is newly seen."""
    now = datetime.now(timezone.utc).isoformat()
    oid = opportunity_id(opp.url)
    existing = conn.execute("SELECT id FROM opportunities WHERE id = ?", (oid,)).fetchone()
    conn.execute(
        """
        INSERT INTO opportunities
            (id, title, url, source, category, description, published_date,
             first_seen, last_seen, match_score, matched_personas, matched_keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            category=excluded.category,
            description=excluded.description,
            published_date=excluded.published_date,
            last_seen=excluded.last_seen,
            match_score=excluded.match_score,
            matched_personas=excluded.matched_personas,
            matched_keywords=excluded.matched_keywords
        """,
        (
            oid, opp.title, opp.url, opp.source, opp.category, opp.description,
            opp.published_date, now, now, opp.match_score,
            ",".join(opp.matched_personas), ",".join(opp.matched_keywords),
        ),
    )
    return existing is None


def fetch_all(conn: sqlite3.Connection, min_score: float = 0.0):
    cur = conn.execute(
        "SELECT title, url, source, category, description, published_date, "
        "first_seen, last_seen, match_score, matched_personas, matched_keywords "
        "FROM opportunities WHERE match_score >= ? ORDER BY first_seen DESC",
        (min_score,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
