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
