"""Database engine and sessions (SQLAlchemy 2). Works with SQLite and Postgres."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


_engine = None
_Session: sessionmaker | None = None


def configure(url: str | None = None):
    """(Re)connect. Tests call this with a temporary database."""
    global _engine, _Session
    url = url or config.DATABASE_URL
    kwargs = {}
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    _engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys = ON")
    _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def engine():
    if _engine is None:
        configure()
    return _engine


SCHEMA_LOCK = 724_106  # Postgres advisory lock id for schema setup


def create_all():
    """Create tables and add any new columns. Several processes may start at once (API workers, the jobs
    worker), so on Postgres this runs under an advisory lock: one sets up, the others wait."""
    from sqlalchemy import inspect, text

    from . import models  # noqa: F401  (register tables)

    eng = engine()
    with eng.begin() as conn:
        if eng.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SCHEMA_LOCK})
        Base.metadata.create_all(conn)
        insp = inspect(conn)
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:  # tiny forward-only migration for new nullable columns
                    ddl = col.type.compile(eng.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


@contextmanager
def session() -> Session:
    if _Session is None:
        configure()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
