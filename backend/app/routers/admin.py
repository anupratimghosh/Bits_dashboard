"""Weekly upload endpoint and the unmatched-author review queue."""
import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from ..db import engine, q
from ..filters import like
from ..ingest import masters, scopus

router = APIRouter(prefix="/api", tags=["admin"])

MASTER_LOADERS = {
    "irins": masters.load_irins,
    "sjr": masters.load_sjr,
    "citescore": masters.load_citescore,
    "wos": masters.load_wos,
}


def _save_upload(upload: UploadFile) -> Path:
    if not upload.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Please upload an .xlsx or .xls file")
    tmp = Path(tempfile.mkdtemp()) / upload.filename
    with tmp.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return tmp


@router.post("/upload/scopus")
async def upload_scopus(
    file: UploadFile = File(...),
    uploaded_by: str = Form("web"),
    snapshot_date: str = Form(None),
):
    """The weekly drop. Upserts on Scopus EID, so re-uploading the same file or
    an overlapping export updates rather than duplicates."""
    # parsed before the file is saved: a bad date is the caller's mistake, and
    # raising here avoids leaving the temp directory behind
    try:
        snap = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    except ValueError:
        raise HTTPException(400, f"snapshot_date must be YYYY-MM-DD, got {snapshot_date!r}")

    path = _save_upload(file)
    try:
        stats = scopus.ingest_scopus(
            path, filename=file.filename, uploaded_by=uploaded_by, snapshot=snap
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    return stats


@router.post("/upload/master/{kind}")
async def upload_master(
    kind: str, file: UploadFile = File(...), metric_year: int = Form(2025)
):
    """Annual refresh for IRINS / SJR / CiteScore / WoS.

    Re-running the Scopus ingest afterwards re-attributes existing publications
    against the new master, which is how newly-added faculty pick up their back
    catalogue.
    """
    if kind not in MASTER_LOADERS:
        raise HTTPException(400, f"kind must be one of {list(MASTER_LOADERS)}")
    path = _save_upload(file)
    try:
        with engine.begin() as conn:
            batch_id = conn.execute(
                text(
                    "INSERT INTO upload_batch (filename, kind, status) "
                    "VALUES (:f, :k, 'pending')"
                ),
                {"f": file.filename, "k": kind},
            ).lastrowid
        loader = MASTER_LOADERS[kind]
        try:
            result = loader(path) if kind == "irins" else loader(path, metric_year)
        except ValueError as exc:
            # a renamed or missing column -- refuse rather than write NULLs over
            # good data, and tell the user exactly which column moved
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE upload_batch SET status = 'failed', message = :m "
                         "WHERE id = :b"),
                    {"m": str(exc), "b": batch_id},
                )
            raise HTTPException(400, str(exc))

        if kind == "irins":
            # faculty campus/department are copied onto publication_author, so a
            # transfer or a newly-added professor only takes effect once those
            # copies are rewritten
            result["resync"] = scopus.resync_faculty()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE upload_batch SET status = 'success', rows_total = :n, "
                    "message = :m WHERE id = :b"
                ),
                {"n": list(result.values())[0], "m": str(result), "b": batch_id},
            )
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    return {"kind": kind, **result}


@router.post("/admin/resync")
def resync():
    """Re-apply faculty matching to every publication already stored.

    Runs automatically after an IRINS upload; exposed separately for when the
    faculty master was loaded from the command line, or after editing aliases.
    """
    return scopus.resync_faculty()


@router.get("/upload/batches")
def list_batches(limit: int = Query(25)):
    return q(
        "SELECT * FROM upload_batch ORDER BY id DESC LIMIT :l", l=limit
    )


# ------------------------------------------------------------- review queue

@router.get("/admin/unmatched")
def unmatched(
    status: str = Query("open"),
    priority_only: bool = Query(True),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """BITS-affiliated authors with no IRINS match.

    `priority_only` (the default) restricts the queue to publications where NO
    author could be resolved -- those are the ones missing entirely from the
    faculty and department views. Turning it off also lists co-authors on
    already-attributed papers, most of whom are research scholars rather than
    faculty.
    """
    where = ["ua.status = :status"]
    params = {"status": status}
    if priority_only:
        where.append("p.faculty_matched = 0")
    if search:
        where.append("(ua.raw_name LIKE :s ESCAPE '!' OR p.title LIKE :s ESCAPE '!')")
        params["s"] = like(search)
    w = " AND ".join(where)

    items = q(
        f"""SELECT ua.id, ua.scopus_author_id, ua.raw_name, ua.raw_affiliation,
                   ua.status, c.name AS guessed_campus, ua.guessed_campus_id,
                   p.id AS publication_id, p.title, p.year, p.doi,
                   p.faculty_matched
            FROM unmatched_author ua
            JOIN publication p ON p.id = ua.publication_id
            LEFT JOIN campus c ON c.id = ua.guessed_campus_id
            WHERE {w}
            ORDER BY p.year DESC, ua.id
            LIMIT :limit OFFSET :offset""",
        **params, limit=page_size, offset=(page - 1) * page_size,
    )
    total = q(
        f"""SELECT COUNT(*) AS n FROM unmatched_author ua
            JOIN publication p ON p.id = ua.publication_id WHERE {w}""",
        **params,
    )[0]["n"]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


class ResolveBody(BaseModel):
    faculty_id: int


@router.post("/admin/unmatched/{item_id}/resolve")
def resolve_unmatched(item_id: int, body: ResolveBody):
    """Map an unmatched author to a faculty member.

    The mapping is written to author_alias keyed by Scopus Author ID, so every
    future upload matches this author automatically -- the fix is permanent, not
    per-publication.
    """
    rows = q(
        "SELECT ua.*, p.id AS pub_id FROM unmatched_author ua "
        "JOIN publication p ON p.id = ua.publication_id WHERE ua.id = :id",
        id=item_id,
    )
    if not rows:
        raise HTTPException(404, "Queue item not found")
    item = rows[0]
    fac = q(
        "SELECT id, campus_id, department_id FROM faculty WHERE id = :id",
        id=body.faculty_id,
    )
    if not fac:
        raise HTTPException(404, "Faculty not found")
    fac = fac[0]

    with engine.begin() as conn:
        if item["scopus_author_id"]:
            conn.execute(
                text(
                    "INSERT INTO author_alias (scopus_author_id, faculty_id) "
                    "VALUES (:s, :f) ON DUPLICATE KEY UPDATE faculty_id = VALUES(faculty_id)"
                ),
                {"s": item["scopus_author_id"], "f": fac["id"]},
            )
            # a match overrides an earlier 'not a faculty member' ruling
            conn.execute(
                text("DELETE FROM author_ignored WHERE scopus_author_id = :s"),
                {"s": item["scopus_author_id"]},
            )
            # apply retroactively to every publication already holding this ID
            conn.execute(
                text(
                    "UPDATE publication_author SET faculty_id = :f, campus_id = :c, "
                    "department_id = :d, is_bits = 1 WHERE scopus_author_id = :s"
                ),
                {"f": fac["id"], "c": fac["campus_id"], "d": fac["department_id"],
                 "s": item["scopus_author_id"]},
            )
            conn.execute(
                text(
                    "UPDATE unmatched_author ua "
                    "JOIN publication_author pa ON pa.id = ua.publication_author_id "
                    "SET ua.status = 'resolved', ua.resolved_faculty_id = :f, "
                    "    ua.resolved_at = NOW() "
                    # `<> 'resolved'` rather than `= 'open'`: an explicit match
                    # must also override an earlier 'not a faculty member'
                    # ruling, which is now durable in author_ignored
                    "WHERE pa.scopus_author_id = :s AND ua.status <> 'resolved'"
                ),
                {"f": fac["id"], "s": item["scopus_author_id"]},
            )
        else:
            conn.execute(
                text(
                    "UPDATE publication_author SET faculty_id = :f, campus_id = :c, "
                    "department_id = :d, is_bits = 1 WHERE id = :pa"
                ),
                {"f": fac["id"], "c": fac["campus_id"], "d": fac["department_id"],
                 "pa": item["publication_author_id"]},
            )
            conn.execute(
                text(
                    "UPDATE unmatched_author SET status = 'resolved', "
                    "resolved_faculty_id = :f, resolved_at = NOW() WHERE id = :id"
                ),
                {"f": fac["id"], "id": item_id},
            )
        # refresh the faculty_matched flag on every affected publication
        conn.execute(
            text(
                """UPDATE publication p SET p.faculty_matched = (
                     SELECT COUNT(*) > 0 FROM publication_author pa
                     WHERE pa.publication_id = p.id AND pa.faculty_id IS NOT NULL)
                   WHERE p.id IN (
                     SELECT publication_id FROM publication_author
                     WHERE faculty_id = :f)"""
            ),
            {"f": fac["id"]},
        )
    return {"resolved": True, "faculty_id": fac["id"]}


@router.post("/admin/unmatched/{item_id}/ignore")
def ignore_unmatched(item_id: int):
    """Not a faculty member (research scholar, visiting co-author) -- drop it
    from the queue without touching the publication.

    The ruling is written to `author_ignored`, keyed by Scopus Author ID, for the
    same reason a match is written to `author_alias`: the weekly ingest rebuilds
    publication_author wholesale and the queue row cascades away with it, so a
    status stored only on that row would not survive the next upload. Like a
    match, the decision applies to every publication by that author, not just
    this one.
    """
    rows = q(
        "SELECT id, scopus_author_id, raw_name FROM unmatched_author WHERE id = :id",
        id=item_id,
    )
    if not rows:
        raise HTTPException(404, "Queue item not found")
    item = rows[0]

    with engine.begin() as conn:
        if item["scopus_author_id"]:
            conn.execute(
                text(
                    "INSERT INTO author_ignored (scopus_author_id, raw_name) "
                    "VALUES (:s, :n) ON DUPLICATE KEY UPDATE raw_name = VALUES(raw_name)"
                ),
                {"s": item["scopus_author_id"], "n": item["raw_name"]},
            )
            conn.execute(
                text(
                    "UPDATE unmatched_author SET status = 'ignored' "
                    "WHERE scopus_author_id = :s AND status = 'open'"
                ),
                {"s": item["scopus_author_id"]},
            )
        else:
            # no Scopus ID to key on: the best we can do is this one row
            conn.execute(
                text("UPDATE unmatched_author SET status = 'ignored' WHERE id = :id"),
                {"id": item_id},
            )
    return {"ignored": True}


@router.get("/admin/stats")
def admin_stats():
    return {
        "publications": q("SELECT COUNT(*) AS n FROM publication")[0]["n"],
        "bits_publications": q(
            "SELECT COUNT(*) AS n FROM publication WHERE is_bits = 1"
        )[0]["n"],
        "attributed_publications": q(
            "SELECT COUNT(*) AS n FROM publication WHERE is_bits = 1 AND faculty_matched = 1"
        )[0]["n"],
        "faculty": q("SELECT COUNT(*) AS n FROM faculty")[0]["n"],
        "faculty_with_scopus_id": q(
            "SELECT COUNT(*) AS n FROM faculty WHERE scopus_author_id IS NOT NULL"
        )[0]["n"],
        "journals": q("SELECT COUNT(*) AS n FROM journal")[0]["n"],
        "journal_metrics": q("SELECT COUNT(*) AS n FROM journal_metric")[0]["n"],
        "open_queue": q(
            """SELECT COUNT(*) AS n FROM unmatched_author ua
               JOIN publication p ON p.id = ua.publication_id
               WHERE ua.status = 'open' AND p.faculty_matched = 0"""
        )[0]["n"],
        "last_upload": (q("SELECT * FROM upload_batch ORDER BY id DESC LIMIT 1") or [None])[0],
    }
