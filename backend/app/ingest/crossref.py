"""Publication dates from Crossref, for financial-year quarters.

A Scopus export carries only the year, so after each upload every BITS paper
with a DOI and no date yet is looked up on the public Crossref API. Only the
DOI leaves this machine.

A date is stored only when Crossref gives at least a month -- a year alone
cannot place a paper in a quarter, so the paper stays undated rather than being
guessed into one. Undated papers are retried after RETRY_DAYS (an article in
press often gains its issue date later); network failures are retried on the
next run because they leave `date_checked_at` unset.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from sqlalchemy import text

from ..db import engine

API = "https://api.crossref.org/works/"
RETRY_DAYS = 28
WORKERS = 4
TIMEOUT = 20
ATTEMPTS = 3

# Crossref asks clients to identify themselves; a contact address puts requests
# in its faster "polite" pool. Opt-in, so nobody's address is sent by default.
_MAILTO = os.getenv("CROSSREF_MAILTO", "").strip()
_UA = "BITS-Research-Dashboard/1.0" + (f" (mailto:{_MAILTO})" if _MAILTO else "")

# print first: Scopus's Year is the cover (issue) year, which is the print date
_DATE_FIELDS = [
    ("published-print", "crossref-print"),
    ("published-online", "crossref-online"),
    ("issued", "crossref-issued"),
]


def pick_date(message, scopus_year):
    """Best (date, source) from a Crossref work record, or (None, None).

    Prefers a candidate whose year agrees with Scopus, so the quarter view and
    the year view put the paper in the same year wherever Crossref allows it.
    """
    candidates = []
    for field, source in _DATE_FIELDS:
        parts = ((message.get(field) or {}).get("date-parts") or [[]])[0] or []
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        try:
            d = date(parts[0], parts[1], parts[2] if len(parts) > 2 and parts[2] else 1)
        except (TypeError, ValueError):
            continue
        candidates.append((d, source))
    if not candidates:
        return None, None
    for d, source in candidates:
        if scopus_year and d.year == scopus_year:
            return d, source
    return candidates[0]


def _fetch(doi):
    """('ok', message) | ('missing', None) | ('error', None)

    Rate limiting (429) and server or network hiccups are retried with a short
    backoff; anything still failing is left for the next run.
    """
    url = API + urllib.parse.quote(doi.strip(), safe="/:;()._-")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return "ok", json.load(res).get("message") or {}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return "missing", None
            if exc.code != 429 and exc.code < 500:
                return "error", None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
    return "error", None


def fill_pub_dates(limit=None):
    """Look up dates for papers that need one. Returns counts for the caller."""
    sql = f"""SELECT id, doi, year FROM publication
              WHERE is_bits = 1 AND doi IS NOT NULL AND doi <> ''
                AND pub_date IS NULL
                AND (date_checked_at IS NULL
                     OR date_checked_at < NOW() - INTERVAL {RETRY_DAYS} DAY)
              ORDER BY id"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    with engine.connect() as conn:
        todo = conn.execute(text(sql)).mappings().all()

    stats = {"checked": len(todo), "dated": 0, "year_only": 0, "not_found": 0, "errors": 0}
    if not todo:
        return stats

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda r: _fetch(r["doi"]), todo))

    with engine.begin() as conn:
        for row, (status, message) in zip(todo, results):
            if status == "error":
                stats["errors"] += 1
                continue  # date_checked_at stays as-is, so the next run retries
            d, source = pick_date(message, row["year"]) if status == "ok" else (None, None)
            if d:
                stats["dated"] += 1
            elif status == "ok":
                stats["year_only"] += 1
            else:
                stats["not_found"] += 1
            conn.execute(
                text(
                    "UPDATE publication SET pub_date = :d, pub_date_source = :s, "
                    "date_checked_at = NOW() WHERE id = :id"
                ),
                {"d": d, "s": source, "id": row["id"]},
            )
    return stats
