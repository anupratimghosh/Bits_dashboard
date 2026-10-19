from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _coerce(v):
    """MySQL returns COUNT/SUM as Decimal; hand the API clean ints and floats."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return v


def q(sql: str, **params):
    """Run a read-only query and return a list of dicts."""
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [{k: _coerce(v) for k, v in r.items()} for r in rows]


# Columns added after the first release. schema.sql only runs CREATE TABLE IF
# NOT EXISTS, which leaves an existing database without them, so they are added
# here on startup -- idempotent, and a no-op once the columns exist.
_ADDED_COLUMNS = [
    ("publication", "pub_date", "DATE NULL AFTER year"),
    ("publication", "pub_date_source", "VARCHAR(24) NULL AFTER pub_date"),
    ("publication", "date_checked_at", "DATETIME NULL AFTER pub_date_source"),
]
_ADDED_INDEXES = [("publication", "ix_pub_date", "(pub_date)")]


def ensure_schema():
    with engine.begin() as conn:
        for table, col, ddl in _ADDED_COLUMNS:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
                    "AND table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": col},
            ).first()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        for table, name, cols in _ADDED_INDEXES:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE() "
                    "AND table_name = :t AND index_name = :i"
                ),
                {"t": table, "i": name},
            ).first()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD INDEX {name} {cols}"))
