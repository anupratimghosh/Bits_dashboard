"""Weekly Scopus upload.

Idempotent by design: publications are upserted on their Scopus EID, so
re-uploading a file or uploading overlapping exports never duplicates a record.
Existing papers get a refreshed citation count plus a new dated snapshot, so the
citation trend survives even though the source file only ever shows 'today'.
"""
from datetime import date

import pandas as pd
from sqlalchemy import text

from ..db import engine
from .masters import JournalRegistry, _lookup_id
from .normalize import (
    CAMPUSES,
    campus_from_affiliation,
    clean_numlike,
    clean_str,
    is_bits_affiliation,
    norm_issn,
    open_access_flag,
    parse_author_full_names,
    parse_authors_with_affiliations,
    split_semicolon,
    to_int,
)

REQUIRED_COLUMNS = ["Authors", "Title", "Year", "Source title", "EID"]

PUB_INSERT = text(
    """INSERT INTO publication
         (eid, title, year, document_type, doi, link, abstract, cited_by,
          journal_id, source_title, issn_raw, issn_norm, isbn, volume, issue,
          art_no, page_start, page_end, publisher, open_access, is_open_access,
          funding_details, correspondence, affiliations_raw, is_bits,
          faculty_matched, first_seen_batch_id, last_batch_id)
       VALUES
         (:eid, :title, :year, :document_type, :doi, :link, :abstract, :cited_by,
          :journal_id, :source_title, :issn_raw, :issn_norm, :isbn, :volume, :issue,
          :art_no, :page_start, :page_end, :publisher, :open_access, :is_open_access,
          :funding_details, :correspondence, :affiliations_raw, :is_bits,
          :faculty_matched, :batch_id, :batch_id)
       ON DUPLICATE KEY UPDATE
         title = VALUES(title), year = VALUES(year),
         document_type = VALUES(document_type), doi = VALUES(doi),
         link = VALUES(link), abstract = VALUES(abstract),
         cited_by = VALUES(cited_by), journal_id = VALUES(journal_id),
         source_title = VALUES(source_title), issn_raw = VALUES(issn_raw),
         issn_norm = VALUES(issn_norm), isbn = VALUES(isbn),
         volume = VALUES(volume), issue = VALUES(issue), art_no = VALUES(art_no),
         page_start = VALUES(page_start), page_end = VALUES(page_end),
         publisher = VALUES(publisher), open_access = VALUES(open_access),
         is_open_access = VALUES(is_open_access),
         funding_details = VALUES(funding_details),
         correspondence = VALUES(correspondence),
         affiliations_raw = VALUES(affiliations_raw), is_bits = VALUES(is_bits),
         faculty_matched = VALUES(faculty_matched), last_batch_id = VALUES(last_batch_id),
         id = LAST_INSERT_ID(id)"""
)


def _author_rows(row):
    """Zip the four parallel author columns Scopus exports into one list.

    They are normally the same length; when Scopus truncates one of them we fall
    back to whatever is present rather than dropping the author entirely.
    """
    ids = split_semicolon(row.get("Author(s) ID"))
    short = split_semicolon(row.get("Authors"))
    full = parse_author_full_names(row.get("Author full names"))
    affil = parse_authors_with_affiliations(row.get("Authors with affiliations"))
    n = max(len(ids), len(short), len(full), len(affil))
    out = []
    for i in range(n):
        aid = ids[i] if i < len(ids) else None
        fname = full[i][0] if i < len(full) else None
        if i < len(full) and full[i][1]:
            aid = aid or full[i][1]
        out.append(
            {
                "seq": i + 1,
                "scopus_author_id": clean_str(aid, 32),
                "raw_name": clean_str(short[i] if i < len(short) else None, 255),
                "full_name": clean_str(fname, 255),
                "affiliation": affil[i][1] if i < len(affil) else None,
            }
        )
    return out


def _clear_matched_ignores(conn):
    """An author ruled 'not a faculty member' who now matches a professor (added
    to IRINS later, or a manual match) was a faculty member after all: drop the
    ruling and close their queue rows, so the Ignored list shows only authors
    who are still unmatched."""
    conn.execute(
        text(
            "DELETE ai FROM author_ignored ai "
            "JOIN publication_author pa ON pa.scopus_author_id = ai.scopus_author_id "
            "WHERE pa.faculty_id IS NOT NULL"
        )
    )
    conn.execute(
        text(
            "UPDATE unmatched_author ua "
            "JOIN publication_author pa ON pa.id = ua.publication_author_id "
            "SET ua.status = 'resolved', ua.resolved_faculty_id = pa.faculty_id, "
            "    ua.resolved_at = NOW() "
            "WHERE pa.faculty_id IS NOT NULL AND ua.status = 'ignored'"
        )
    )


def _load_faculty_index(conn):
    """scopus_author_id -> (faculty_id, campus_id, department_id), including
    every extra ID IRINS lists and manual overrides from the review queue."""
    idx = {}
    for r in conn.execute(
        text(
            "SELECT scopus_author_id, id, campus_id, department_id FROM faculty "
            "WHERE scopus_author_id IS NOT NULL"
        )
    ):
        idx[r[0]] = (r[1], r[2], r[3])
    # further IDs IRINS lists for the same professor
    for r in conn.execute(
        text(
            "SELECT x.scopus_author_id, f.id, f.campus_id, f.department_id "
            "FROM faculty_scopus_id x JOIN faculty f ON f.id = x.faculty_id"
        )
    ):
        idx[r[0]] = (r[1], r[2], r[3])
    for r in conn.execute(
        text(
            "SELECT a.scopus_author_id, f.id, f.campus_id, f.department_id "
            "FROM author_alias a JOIN faculty f ON f.id = a.faculty_id"
        )
    ):
        idx[r[0]] = (r[1], r[2], r[3])
    return idx


def ingest_scopus(path, filename=None, uploaded_by=None, snapshot=None):
    df = pd.read_excel(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Not a Scopus export - missing columns: {', '.join(missing)}")

    snapshot = snapshot or date.today()
    stats = {"total": len(df), "new": 0, "updated": 0, "unmatched": 0, "non_bits": 0}

    with engine.begin() as conn:
        batch_id = conn.execute(
            text(
                "INSERT INTO upload_batch (filename, kind, uploaded_by, rows_total, status) "
                "VALUES (:f, 'scopus', :u, :n, 'pending')"
            ),
            {"f": filename or str(path), "u": uploaded_by, "n": len(df)},
        ).lastrowid

        reg = JournalRegistry(conn)
        fac_idx = _load_faculty_index(conn)
        # 'not a faculty member' rulings: the queue rows themselves cascade away
        # when publication_author is rebuilt below, so the decision has to be
        # re-applied from author_ignored on every ingest
        ignored_ids = {
            r[0] for r in conn.execute(text("SELECT scopus_author_id FROM author_ignored"))
        }
        camp_cache, dept_cache = {}, {}
        for c in CAMPUSES:
            _lookup_id(conn, "campus", c, camp_cache)

        existing = {
            r[0] for r in conn.execute(text("SELECT eid FROM publication"))
        }

        for _, row in df.iterrows():
            eid = clean_str(row.get("EID"), 64)
            if not eid:
                continue

            issn_norm = norm_issn(row.get("ISSN"))
            journal_id = None
            if issn_norm:
                journal_id = reg.resolve(
                    [issn_norm],
                    title=row.get("Source title"),
                    publisher=row.get("Publisher"),
                )

            authors = _author_rows(row)
            affil_raw = clean_str(row.get("Affiliations"))

            resolved = []
            for a in authors:
                bits = is_bits_affiliation(a["affiliation"])
                fac = fac_idx.get(a["scopus_author_id"]) if a["scopus_author_id"] else None
                if fac:
                    fid, cid, did = fac
                    bits = True          # IRINS membership is proof of BITS affiliation
                else:
                    fid, did = None, None
                    cid = (
                        camp_cache.get(campus_from_affiliation(a["affiliation"]))
                        if bits
                        else None
                    )
                a.update(
                    {"is_bits": 1 if bits else 0, "faculty_id": fid,
                     "campus_id": cid, "department_id": did}
                )
                resolved.append(a)

            is_bits = 1 if any(a["is_bits"] for a in resolved) else 0
            if not is_bits and is_bits_affiliation(affil_raw):
                is_bits = 1
            faculty_matched = 1 if any(a["faculty_id"] for a in resolved) else 0
            if not is_bits:
                stats["non_bits"] += 1
            if is_bits and not faculty_matched:
                stats["unmatched"] += 1

            pub_id = conn.execute(
                PUB_INSERT,
                {
                    "eid": eid,
                    "title": clean_str(row.get("Title"), 1024) or "(untitled)",
                    "year": to_int(row.get("Year")),
                    "document_type": clean_str(row.get("Document Type"), 64),
                    "doi": clean_str(row.get("DOI"), 255),
                    "link": clean_str(row.get("Link"), 1024),
                    "abstract": clean_str(row.get("Abstract")),
                    "cited_by": to_int(row.get("Cited by")) or 0,
                    "journal_id": journal_id,
                    "source_title": clean_str(row.get("Source title"), 512),
                    "issn_raw": clean_str(row.get("ISSN"), 64),
                    "issn_norm": issn_norm,
                    "isbn": clean_str(row.get("ISBN"), 64),
                    "volume": clean_numlike(row.get("Volume"), 64),
                    "issue": clean_numlike(row.get("Issue"), 64),
                    "art_no": clean_numlike(row.get("Art. No."), 64),
                    "page_start": clean_numlike(row.get("Page start"), 32),
                    "page_end": clean_numlike(row.get("Page end"), 32),
                    "publisher": clean_str(row.get("Publisher"), 255),
                    "open_access": clean_str(row.get("Open Access"), 255),
                    "is_open_access": open_access_flag(row.get("Open Access")),
                    "funding_details": clean_str(row.get("Funding Details")),
                    "correspondence": clean_str(row.get("Correspondence Address")),
                    "affiliations_raw": affil_raw,
                    "is_bits": is_bits,
                    "faculty_matched": faculty_matched,
                    "batch_id": batch_id,
                },
            ).lastrowid

            if eid in existing:
                stats["updated"] += 1
            else:
                stats["new"] += 1
                existing.add(eid)

            # authors are rewritten wholesale: cheap, and it lets a corrected
            # IRINS master re-attribute old papers on the next upload
            conn.execute(
                text("DELETE FROM publication_author WHERE publication_id = :p"),
                {"p": pub_id},
            )
            for a in resolved:
                pa_id = conn.execute(
                    text(
                        """INSERT INTO publication_author
                             (publication_id, author_seq, scopus_author_id, raw_name,
                              full_name, raw_affiliation, faculty_id, is_bits,
                              campus_id, department_id)
                           VALUES (:p, :seq, :sid, :rn, :fn, :aff, :fid, :bits, :cid, :did)"""
                    ),
                    {
                        "p": pub_id, "seq": a["seq"], "sid": a["scopus_author_id"],
                        "rn": a["raw_name"], "fn": a["full_name"],
                        "aff": a["affiliation"], "fid": a["faculty_id"],
                        "bits": a["is_bits"], "cid": a["campus_id"],
                        "did": a["department_id"],
                    },
                ).lastrowid
                if a["is_bits"] and not a["faculty_id"]:
                    conn.execute(
                        text(
                            """INSERT INTO unmatched_author
                                 (publication_id, publication_author_id, scopus_author_id,
                                  raw_name, raw_affiliation, guessed_campus_id, status)
                               VALUES (:p, :pa, :sid, :rn, :aff, :cid, :st)
                               ON DUPLICATE KEY UPDATE raw_name = VALUES(raw_name)"""
                        ),
                        {
                            "p": pub_id, "pa": pa_id, "sid": a["scopus_author_id"],
                            "rn": a["raw_name"], "aff": a["affiliation"],
                            "cid": a["campus_id"],
                            "st": "ignored"
                                  if a["scopus_author_id"] in ignored_ids else "open",
                        },
                    )

            conn.execute(
                text(
                    """INSERT INTO publication_citation
                         (publication_id, snapshot_date, cited_by, batch_id)
                       VALUES (:p, :d, :c, :b)
                       ON DUPLICATE KEY UPDATE cited_by = VALUES(cited_by)"""
                ),
                {"p": pub_id, "d": snapshot, "c": to_int(row.get("Cited by")) or 0,
                 "b": batch_id},
            )

        conn.execute(
            text(
                "UPDATE upload_batch SET rows_new = :n, rows_updated = :u, "
                "rows_unmatched = :m, status = 'success' WHERE id = :b"
            ),
            {"n": stats["new"], "u": stats["updated"], "m": stats["unmatched"],
             "b": batch_id},
        )
        _clear_matched_ignores(conn)

    stats["batch_id"] = batch_id
    return stats


def resync_faculty():
    """Re-apply faculty matching to every publication already in the database.

    `publication_author` stores campus and department alongside the faculty link,
    because that is what makes the campus/department aggregates a single join.
    The cost is that those copies go stale when IRINS changes: a professor who
    transfers from Pilani to Goa gets a new campus on their profile while their
    existing publications still credit Pilani.

    This walks every author row again against the current faculty master (and any
    manual aliases), rewrites the links, refreshes `publication.faculty_matched`,
    and reopens or closes review-queue entries to match. It is safe to run at any
    time and is called automatically after an IRINS upload.
    """
    stats = {"authors_checked": 0, "authors_relinked": 0, "publications_touched": 0}

    with engine.begin() as conn:
        fac_idx = _load_faculty_index(conn)
        camp_cache = {
            r[1]: r[0] for r in conn.execute(text("SELECT id, name FROM campus"))
        }

        rows = conn.execute(
            text(
                "SELECT id, publication_id, scopus_author_id, raw_affiliation, "
                "       faculty_id, campus_id, department_id, is_bits "
                "FROM publication_author"
            )
        ).mappings().all()

        changed_pubs = set()
        for r in rows:
            stats["authors_checked"] += 1
            fac = fac_idx.get(r["scopus_author_id"]) if r["scopus_author_id"] else None
            if fac:
                fid, cid, did = fac
                bits = 1
            else:
                fid, did = None, None
                bits = 1 if is_bits_affiliation(r["raw_affiliation"]) else 0
                cid = (
                    camp_cache.get(campus_from_affiliation(r["raw_affiliation"]))
                    if bits
                    else None
                )
            if (fid, cid, did, bits) == (
                r["faculty_id"], r["campus_id"], r["department_id"], r["is_bits"]
            ):
                continue

            conn.execute(
                text(
                    "UPDATE publication_author SET faculty_id = :f, campus_id = :c, "
                    "department_id = :d, is_bits = :b WHERE id = :id"
                ),
                {"f": fid, "c": cid, "d": did, "b": bits, "id": r["id"]},
            )
            stats["authors_relinked"] += 1
            changed_pubs.add(r["publication_id"])

        if changed_pubs:
            conn.execute(
                text(
                    """UPDATE publication p SET p.faculty_matched = (
                         SELECT COUNT(*) > 0 FROM publication_author pa
                         WHERE pa.publication_id = p.id AND pa.faculty_id IS NOT NULL)"""
                )
            )
            # a now-matched author leaves the queue; a newly unmatched one joins it
            conn.execute(
                text(
                    "UPDATE unmatched_author ua "
                    "JOIN publication_author pa ON pa.id = ua.publication_author_id "
                    "SET ua.status = 'resolved', ua.resolved_faculty_id = pa.faculty_id, "
                    "    ua.resolved_at = NOW() "
                    "WHERE pa.faculty_id IS NOT NULL AND ua.status = 'open'"
                )
            )
            conn.execute(
                text(
                    """INSERT INTO unmatched_author
                         (publication_id, publication_author_id, scopus_author_id,
                          raw_name, raw_affiliation, guessed_campus_id, status)
                       SELECT pa.publication_id, pa.id, pa.scopus_author_id,
                              pa.raw_name, pa.raw_affiliation, pa.campus_id,
                              IF(ai.scopus_author_id IS NULL, 'open', 'ignored')
                       FROM publication_author pa
                       LEFT JOIN author_ignored ai
                              ON ai.scopus_author_id = pa.scopus_author_id
                       WHERE pa.is_bits = 1 AND pa.faculty_id IS NULL
                       ON DUPLICATE KEY UPDATE
                         -- An admin's 'not a faculty member' ruling is a
                         -- judgement call and must survive a re-sync; only
                         -- previously-resolved entries are reopened.
                         status = IF(status = 'ignored', 'ignored', VALUES(status)),
                         resolved_faculty_id = IF(status = 'ignored',
                                                  resolved_faculty_id, NULL),
                         resolved_at = IF(status = 'ignored', resolved_at, NULL)"""
                )
            )

        _clear_matched_ignores(conn)
        stats["publications_touched"] = len(changed_pubs)

    return stats
