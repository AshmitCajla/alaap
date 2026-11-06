"""SQLite storage. One connection per call so Gradio's worker threads are safe."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS business (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,              -- salon, clinic, ...
    phone TEXT,
    owner_phone TEXT,
    address TEXT,
    city TEXT,
    languages TEXT,                  -- comma separated
    about TEXT,
    skills TEXT NOT NULL             -- enabled skills, comma separated
);

CREATE TABLE IF NOT EXISTS business_hours (
    business_id INTEGER NOT NULL REFERENCES business(id),
    weekday INTEGER NOT NULL,        -- 0 = Monday
    opens TEXT NOT NULL,             -- HH:MM
    closes TEXT NOT NULL,
    PRIMARY KEY (business_id, weekday)
);

CREATE TABLE IF NOT EXISTS service (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    price_inr INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staff_service (
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    service_id INTEGER NOT NULL REFERENCES service(id),
    PRIMARY KEY (staff_id, service_id)
);

CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    UNIQUE (business_id, phone)
);

CREATE TABLE IF NOT EXISTS appointment (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    business_id INTEGER NOT NULL REFERENCES business(id),
    customer_id INTEGER NOT NULL REFERENCES customer(id),
    service_id INTEGER NOT NULL REFERENCES service(id),
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    start_at TEXT NOT NULL,          -- local time, YYYY-MM-DD HH:MM
    end_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked',   -- booked | cancelled
    channel TEXT,
    conversation_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages waiting to go out on WhatsApp. Sending is Phase 1;
-- the MVP shows them on the owner dashboard.
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    to_phone TEXT NOT NULL,
    kind TEXT NOT NULL,              -- confirmation | reminder | cancellation | owner_alert
    body TEXT NOT NULL,
    send_after TEXT NOT NULL,
    appointment_id INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | sent | cancelled
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS callback (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT,
    phone TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    conversation_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    channel TEXT NOT NULL,
    caller_phone TEXT,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id),
    role TEXT NOT NULL,              -- customer | alaap | tool
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect(path: Path | None = None):
    """Open a connection, commit on success, roll back on error."""
    conn = _connect(path or config.DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def rows(conn: sqlite3.Connection, sql: str, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def row(conn: sqlite3.Connection, sql: str, *args) -> dict | None:
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None
