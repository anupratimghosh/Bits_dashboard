"""Loaders for the reference data that changes annually, not weekly:
IRINS faculty, SJR, CiteScore and Web of Science journal masters.

Journal identity is resolved purely through ISSN: a journal row is created the
first time any of its ISSNs is seen, and every further ISSN variant from any
master is pointed at that same row via `journal_issn`. That is what lets a Scopus
record carrying only a print ISSN pick up metrics filed under the e-ISSN.

Each loader declares the columns it needs (`_SPEC`) and which of them are
non-negotiable (`_REQUIRED`). Headers are matched case- and
punctuation-insensitively, extra columns are ignored, and a missing required
column aborts the load rather than silently writing NULLs over good data.
"""
import pandas as pd
from sqlalchemy import text

from ..db import engine
from .normalize import (
    ColumnMap,
    campus_from_affiliation,
    clean_str,
    norm_quartile,
    split_issns,
    split_scopus_ids,
    to_float,
    to_int,
)


# --------------------------------------------------------------- small helpers

def _exec(conn, sql, rows, chunk=2000):
    if not rows:
        return
    stmt = text(sql)
    for i in range(0, len(rows), chunk):
        conn.execute(stmt, rows[i : i + chunk])


def _lookup_id(conn, table, name, cache):
    """Get-or-create for the campus / department lookup tables."""
    name = clean_str(name)
    if not name:
        return None
    if name in cache:
        return cache[name]
    row = conn.execute(
        text(f"SELECT id FROM {table} WHERE name = :n"), {"n": name}
    ).first()
    if row:
        cache[name] = row[0]
    else:
        res = conn.execute(text(f"INSERT INTO {table} (name) VALUES (:n)"), {"n": name})
        cache[name] = res.lastrowid
    return cache[name]


class JournalRegistry:
    """In-memory ISSN -> journal_id map, flushed to journal/journal_issn."""

    def __init__(self, conn):
        self.conn = conn
        self.by_issn = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT issn_norm, journal_id FROM journal_issn"))
        }

    def resolve(self, issns, title=None, publisher=None, source_id=None,
                authoritative=False):
        """`authoritative` marks the caller as the naming authority for this
        journal. The masters are (they carry the canonical title and publisher);
        the weekly Scopus ingest is not -- it only knows the source title as
        printed on the record, and must not overwrite a master's title with it
        every week. A non-authoritative caller therefore only fills in gaps."""
        issns = [i for i in issns if i]
        if not issns:
            return None
        jid = next((self.by_issn[i] for i in issns if i in self.by_issn), None)
        if jid is None:
            res = self.conn.execute(
                text(
                    "INSERT INTO journal (issn_norm, scopus_source_id, title, publisher) "
                    "VALUES (:i, :s, :t, :p)"
                ),
                {
                    "i": issns[0],
                    "s": source_id,
                    "t": clean_str(title, 512) or issns[0],
                    "p": clean_str(publisher, 255),
                },
            )
            jid = res.lastrowid
        elif source_id or title or publisher:
            # a journal first seen in a Scopus export is titled with its raw
            # source title (or, failing that, its ISSN); this is what upgrades it
            # once a master supplies the real one
            self.conn.execute(
                text(
                    "UPDATE journal SET "
                    "  scopus_source_id = COALESCE(:s, scopus_source_id), "
                    "  publisher = IF(:auth, COALESCE(:p, publisher), "
                    "                        COALESCE(publisher, :p)), "
                    "  title = CASE WHEN :t IS NULL THEN title "
                    "               WHEN :auth THEN :t "
                    "               WHEN title = issn_norm THEN :t "
                    "               ELSE title END "
                    "WHERE id = :j"
                ),
                {
                    "s": source_id,
                    "p": clean_str(publisher, 255),
                    "t": clean_str(title, 512),
                    "auth": 1 if authoritative else 0,
                    "j": jid,
                },
            )
        new = [i for i in issns if i not in self.by_issn]
        if new:
            self.conn.execute(
                text(
                    "INSERT IGNORE INTO journal_issn (issn_norm, journal_id) "
                    "VALUES (:i, :j)"
                ),
                [{"i": i, "j": jid} for i in new],
            )
            for i in new:
                self.by_issn[i] = jid
        return jid


def _upsert_metric(conn, rows, columns):
    """Merge a subset of metric columns into journal_metric without clobbering
    columns owned by the other masters."""
    if not rows:
        return
    cols = ["journal_id", "metric_year"] + columns
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c} = VALUES({c})" for c in columns)
    sql = (
        f"INSERT INTO journal_metric ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    _exec(conn, sql, rows)


def _require_any_issn(cm, source):
    if not any(k in cm.actual for k in ("issn", "print_issn", "e_issn")):
        raise ValueError(
            f"{source}: no ISSN column found. Journal metrics are matched on "
            "ISSN, so at least one of ISSN / Print ISSN / E-ISSN must be present."
        )


# ----------------------------------------------------------------- IRINS

_IRINS_SPEC = {
    "expert_id": ["Expert_ID", "Expert ID"],
    "scopus_id": ["Scopus_ID", "Scopus ID", "ScopusID", "Scopus Author ID"],
    "name": ["Name", "Full Name", "Full_Name"],
    "title": ["Title"],
    "designation": ["Designation"],
    "email": ["Email", "Email_ID"],
    "campus": ["Campus"],
    "department": ["Department"],
    "orcid": ["ORCID_ID", "ORCID", "Orcid Id"],
    "researcher_id": ["Researcher_ID", "Researcher ID"],
    "gscholar": ["Google_Scholar_ID", "Google Scholar ID"],
    "expertise": ["Expertise"],
    "qualification": ["Qualification"],
    "status": ["status_mode", "Status"],
}
# expert_id is required, not optional: it is the only key the upsert below can
# match an existing faculty row on. The Scopus IDs are deliberately released from
# their current owners first, so without Expert_ID nothing would collide and every
# re-upload would insert a duplicate copy of the whole roster.
_IRINS_REQUIRED = ["expert_id", "name", "scopus_id", "campus", "department"]

# spec key -> (faculty column, insert parameter). Only the columns the uploaded
# sheet actually has are overwritten on an existing professor, so a short sheet
# of new joiners cannot blank out everyone else's email or ORCID.
_IRINS_COLUMNS = {
    "name": ("name", "name"),
    "title": ("title", "title"),
    "designation": ("designation", "desig"),
    "email": ("email", "email"),
    "campus": ("campus_id", "campus_id"),
    "department": ("department_id", "dept_id"),
    "orcid": ("orcid_id", "orcid"),
    "researcher_id": ("researcher_id", "rid"),
    "gscholar": ("google_scholar_id", "gs"),
    "expertise": ("expertise", "exp"),
    "qualification": ("qualification", "qual"),
    "status": ("is_active", "active"),
    "scopus_id": ("scopus_author_id", "sid"),
}

# upload result lists are cut to this many names; the counts stay exact
_LIST_CAP = 20


def _capped(items):
    return items if len(items) <= _LIST_CAP else items[:_LIST_CAP] + [f"... and {len(items) - _LIST_CAP} more"]


def load_irins(path, sheet=0):
    """IRINS faculty master -> campus, department, faculty.

    Works for the whole roster and for a sheet of just the new joiners alike:
    rows are upserted on Expert_ID, professors absent from the sheet are left as
    they are, and only the columns the sheet carries are written. Rows that
    cannot be loaded safely are skipped and named in the result rather than
    guessed at.
    """
    df = pd.read_excel(path, sheet_name=sheet)
    cm = ColumnMap(df, _IRINS_SPEC, _IRINS_REQUIRED, source="IRINS master")
    present = [k for k in _IRINS_COLUMNS if k in cm.actual]

    no_expert, bad_campus, dup_expert, bad_sid, dup_sid = [], [], [], [], []

    with engine.begin() as conn:
        dept = {}
        known_depts = {r[0] for r in conn.execute(text("SELECT name FROM department"))}
        camp_ids = {r[1]: r[0] for r in conn.execute(text("SELECT id, name FROM campus"))}
        rows, seen_expert, claimed = [], set(), {}
        for i, r in df.iterrows():
            line = i + 2                     # spreadsheet row number, header is row 1
            name = clean_str(cm.get(r, "name"), 255) or "Unknown"
            expert_id = to_int(cm.get(r, "expert_id"))
            if expert_id is None:
                no_expert.append(f"row {line}: {name}")
                continue
            if expert_id in seen_expert:
                dup_expert.append(f"row {line}: {name} (Expert_ID {expert_id})")
                continue
            seen_expert.add(expert_id)

            # campus spelled any way IRINS writes it ("BITS Pilani, Hyderabad
            # Campus", "K K Birla Goa") resolves to one of the four campuses; an
            # unrecognised one is refused instead of becoming a fifth campus
            raw_campus = clean_str(cm.get(r, "campus"))
            campus = campus_from_affiliation(raw_campus)
            if campus is None:
                bad_campus.append(f"row {line}: {name} (campus '{raw_campus or ''}')")
                continue
            if campus not in camp_ids:
                camp_ids[campus] = _lookup_id(conn, "campus", campus, {})

            ids, rejected = split_scopus_ids(cm.get(r, "scopus_id"))
            if rejected:
                bad_sid.append(f"row {line}: {name} ('{', '.join(rejected)}')")
            # an ID may belong to one professor only -- the first row keeps it
            for sid in [x for x in ids if x in claimed]:
                dup_sid.append(f"{sid}: {claimed[sid]} and {name} (kept for {claimed[sid]})")
                ids.remove(sid)
            for sid in ids:
                claimed[sid] = name

            rows.append(
                {
                    "expert_id": expert_id,
                    "sid": ids[0] if ids else None,
                    "extra_sids": ids[1:],
                    "name": name,
                    "title": clean_str(cm.get(r, "title"), 32),
                    "desig": clean_str(cm.get(r, "designation"), 96),
                    "email": clean_str(cm.get(r, "email"), 255),
                    "campus_id": camp_ids[campus],
                    "dept_id": _lookup_id(conn, "department", cm.get(r, "department"), dept),
                    "orcid": clean_str(cm.get(r, "orcid"), 64),
                    "rid": clean_str(cm.get(r, "researcher_id"), 64),
                    "gs": clean_str(cm.get(r, "gscholar"), 96),
                    "exp": clean_str(cm.get(r, "expertise")),
                    "qual": clean_str(cm.get(r, "qualification"), 128),
                    "active": 0 if clean_str(cm.get(r, "status")) == "I" else 1,
                }
            )
        new_depts = sorted(n for n in dept if clean_str(n) not in known_depts)

        # Who holds each incoming ID today -- as a first ID, an extra ID, or a
        # manual match from the review queue. An ID moving to a different
        # professor is applied (IRINS is the authority) but reported, because a
        # typo in a new joiner's row otherwise silently takes over someone
        # else's publications.
        incoming = {sid: row for row in rows for sid in ([row["sid"]] if row["sid"] else []) + row["extra_sids"]}
        holders = {}
        for sid_chunk in _chunks(list(incoming), 1000):
            binds = {f"i{k}": v for k, v in enumerate(sid_chunk)}
            inlist = ", ".join(":" + k for k in binds)
            for sid, eid, fname, kind in conn.execute(
                text(
                    f"""SELECT f.scopus_author_id, f.expert_id, f.name, 'irins' FROM faculty f
                         WHERE f.scopus_author_id IN ({inlist})
                        UNION ALL
                        SELECT x.scopus_author_id, f.expert_id, f.name, 'irins' FROM faculty_scopus_id x
                          JOIN faculty f ON f.id = x.faculty_id WHERE x.scopus_author_id IN ({inlist})
                        UNION ALL
                        SELECT a.scopus_author_id, f.expert_id, f.name, 'review' FROM author_alias a
                          JOIN faculty f ON f.id = a.faculty_id WHERE a.scopus_author_id IN ({inlist})"""
                ),
                binds,
            ):
                holders.setdefault(sid, []).append((eid, fname, kind))
        moved, stale_alias = [], []
        for sid, row in incoming.items():
            for eid, fname, kind in holders.get(sid, []):
                if eid == row["expert_id"]:
                    continue
                moved.append(f"{sid}: {fname} -> {row['name']}"
                             + (" (was a review-queue match)" if kind == "review" else ""))
                if kind == "review":
                    stale_alias.append(sid)

        # release every incoming ID from wherever it sits now, so the UNIQUE key
        # cannot collide mid-upsert; the writes below re-assign them correctly
        for sid_chunk in _chunks(list(incoming), 1000):
            binds = {f"i{k}": v for k, v in enumerate(sid_chunk)}
            inlist = ", ".join(":" + k for k in binds)
            conn.execute(text(f"UPDATE faculty SET scopus_author_id = NULL WHERE scopus_author_id IN ({inlist})"), binds)
            conn.execute(text(f"DELETE FROM faculty_scopus_id WHERE scopus_author_id IN ({inlist})"), binds)
        for sid_chunk in _chunks(stale_alias, 1000):
            binds = {f"i{k}": v for k, v in enumerate(sid_chunk)}
            conn.execute(
                text(f"DELETE FROM author_alias WHERE scopus_author_id IN ({', '.join(':' + k for k in binds)})"),
                binds,
            )

        existing = {r[0] for r in conn.execute(text("SELECT expert_id FROM faculty WHERE expert_id IS NOT NULL"))}
        cols = ["expert_id"] + [_IRINS_COLUMNS[k][0] for k in present]
        vals = [":expert_id"] + [":" + _IRINS_COLUMNS[k][1] for k in present]
        updates = ", ".join(f"{c} = VALUES({c})" for c in cols[1:])
        _exec(
            conn,
            f"""INSERT INTO faculty ({", ".join(cols)})
                VALUES ({", ".join(vals)})
                ON DUPLICATE KEY UPDATE {updates}""",
            rows,
        )

        # extra IDs: the sheet's list replaces whatever this professor had
        ids_by_expert = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT expert_id, id FROM faculty WHERE expert_id IS NOT NULL"))
        }
        loaded = [ids_by_expert[row["expert_id"]] for row in rows]
        for fac_chunk in _chunks(loaded, 1000):
            binds = {f"i{k}": v for k, v in enumerate(fac_chunk)}
            conn.execute(
                text(f"DELETE FROM faculty_scopus_id WHERE faculty_id IN ({', '.join(':' + k for k in binds)})"),
                binds,
            )
        extras = [
            {"s": sid, "f": ids_by_expert[row["expert_id"]]}
            for row in rows for sid in row["extra_sids"]
        ]
        if extras:
            _exec(conn, "INSERT INTO faculty_scopus_id (scopus_author_id, faculty_id) VALUES (:s, :f)", extras)

    out = {
        "faculty_rows": len(rows),
        "added": sum(1 for row in rows if row["expert_id"] not in existing),
        "updated": sum(1 for row in rows if row["expert_id"] in existing),
        "with_scopus_id": sum(1 for row in rows if row["sid"]),
    }
    if extras:
        out["extra_scopus_ids"] = len(extras)
    warnings = {
        "skipped_no_expert_id": no_expert,
        "skipped_unknown_campus": bad_campus,
        "skipped_duplicate_expert_id": dup_expert,
        "unreadable_scopus_ids": bad_sid,
        "duplicate_scopus_ids": dup_sid,
        "scopus_ids_moved": moved,
        "new_departments": new_depts,
    }
    for key, items in warnings.items():
        if items:
            out[key] = _capped(items)
    out.update(cm.report())
    return out


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


# ------------------------------------------------------------------- SJR

_SJR_SPEC = {
    "issn": ["Issn", "ISSN"],
    "title": ["Title", "Journal Title"],
    "source_id": ["Sourceid", "Source Id", "Scopus Source ID"],
    "publisher": ["Publisher"],
    "publisher_alt": ["Publisher.1"],
    "sjr": ["SJR(Covrt)", "SJR", "SJR (Covrt)"],
    "quartile": ["SJR Best Quartile", "Best Quartile", "Quartile"],
    "h_index": ["H index", "H-Index", "H_index", "Hindex"],
}
_SJR_REQUIRED = ["issn", "sjr", "quartile", "h_index"]


def load_sjr(path, metric_year=2025, sheet=0):
    """SCImago master -> SJR score, best quartile, h-index."""
    df = pd.read_excel(path, sheet_name=sheet)
    cm = ColumnMap(df, _SJR_SPEC, _SJR_REQUIRED, source="SJR master")

    with engine.begin() as conn:
        reg = JournalRegistry(conn)
        rows = []
        for _, r in df.iterrows():
            jid = reg.resolve(
                split_issns(cm.get(r, "issn")),
                title=cm.get(r, "title"),
                publisher=clean_str(cm.get(r, "publisher"))
                or clean_str(cm.get(r, "publisher_alt")),
                source_id=to_int(cm.get(r, "source_id")),
                authoritative=True,
            )
            if not jid:
                continue
            rows.append(
                {
                    "journal_id": jid,
                    "metric_year": metric_year,
                    "sjr": to_float(cm.get(r, "sjr")),
                    "sjr_quartile": norm_quartile(cm.get(r, "quartile")),
                    "h_index": to_int(cm.get(r, "h_index")),
                }
            )
        _upsert_metric(conn, rows, ["sjr", "sjr_quartile", "h_index"])

    return {"journals": len(rows), "metric_year": metric_year, **cm.report()}


# ------------------------------------------------------------- CiteScore

_CITESCORE_SPEC = {
    "issn": ["Issn", "ISSN"],
    "print_issn": ["Print ISSN", "PrintISSN"],
    "e_issn": ["E-ISSN", "eISSN", "Electronic ISSN"],
    "source_id": ["Scopus Source ID", "Sourceid"],
    "title": ["Title", "Journal Title"],
    "publisher": ["Main publisher"],
    "publisher_alt": ["Publisher"],
    "citescore": ["CiteScore"],
    "snip": ["SNIP"],
    "percentile": ["Percentile"],
    "quartile": ["Quartile"],
    "asjc": ["Scopus ASJC Code (Sub-subject Area)", "ASJC", "ASJC Code"],
    "subject": ["Scopus Sub-Subject Area", "Sub-Subject Area", "Subject Area"],
    "open_access": ["Open Access"],
}
_CITESCORE_REQUIRED = ["citescore", "snip"]


def load_citescore(path, metric_year=2025, sheet=0):
    """CiteScore master -> CiteScore, SNIP, plus the ASJC subject taxonomy.

    The file carries one row per journal x subject area (78k rows for 32k
    journals), so journal-level values are taken once and the per-subject
    percentile/quartile rows go to journal_subject. The subject with the best
    percentile becomes the journal's headline CiteScore quartile.
    """
    df = pd.read_excel(path, sheet_name=sheet)
    cm = ColumnMap(df, _CITESCORE_SPEC, _CITESCORE_REQUIRED, source="CiteScore master")
    _require_any_issn(cm, "CiteScore master")

    with engine.begin() as conn:
        reg = JournalRegistry(conn)
        metrics, subjects = {}, []
        for _, r in df.iterrows():
            issns = split_issns(cm.get(r, "issn"))
            if not issns:
                issns = split_issns(cm.get(r, "print_issn")) + split_issns(
                    cm.get(r, "e_issn")
                )
            jid = reg.resolve(
                issns,
                title=cm.get(r, "title"),
                publisher=clean_str(cm.get(r, "publisher"))
                or clean_str(cm.get(r, "publisher_alt")),
                source_id=to_int(cm.get(r, "source_id")),
                authoritative=True,
            )
            if not jid:
                continue

            pct = to_float(cm.get(r, "percentile"))
            # the column ships as a bare integer (1..4) today, but a re-issued
            # file spelling it "Q1" must not silently become NULL -- to_int()
            # cannot read "Q1", and norm_quartile() cannot read a bare 3
            raw_q = cm.get(r, "quartile")
            qtl = norm_quartile(raw_q)
            if qtl is None:
                qnum = to_int(raw_q)
                qtl = f"Q{qnum}" if qnum in (1, 2, 3, 4) else None
            asjc = to_int(cm.get(r, "asjc"))
            subj = clean_str(cm.get(r, "subject"), 160)
            if asjc and subj:
                subjects.append(
                    {
                        "journal_id": jid,
                        "metric_year": metric_year,
                        "asjc_code": asjc,
                        "subject": subj,
                        "percentile": pct,
                        "quartile": qtl,
                    }
                )
            best = metrics.get(jid)
            if best is None or (pct is not None and (best["_pct"] is None or pct > best["_pct"])):
                metrics[jid] = {
                    "journal_id": jid,
                    "metric_year": metric_year,
                    "citescore": to_float(cm.get(r, "citescore")),
                    "snip": to_float(cm.get(r, "snip")),
                    "cs_quartile": qtl,
                    "cs_percentile": pct,
                    "open_access": clean_str(cm.get(r, "open_access"), 16),
                    "_pct": pct,
                }

        rows = []
        for m in metrics.values():
            m.pop("_pct", None)
            rows.append(m)
        _upsert_metric(
            conn, rows, ["citescore", "snip", "cs_quartile", "cs_percentile", "open_access"]
        )
        _exec(
            conn,
            """INSERT INTO journal_subject
                 (journal_id, metric_year, asjc_code, subject, percentile, quartile)
               VALUES (:journal_id, :metric_year, :asjc_code, :subject, :percentile, :quartile)
               ON DUPLICATE KEY UPDATE subject = VALUES(subject),
                 percentile = VALUES(percentile), quartile = VALUES(quartile)""",
            subjects,
        )

    return {
        "journals": len(rows),
        "subject_rows": len(subjects),
        "metric_year": metric_year,
        **cm.report(),
    }


# --------------------------------------------------------- Web of Science

_WOS_SPEC = {
    "issn": ["Issn", "ISSN"],
    "print_issn": ["PrintISSN", "Print ISSN"],
    "e_issn": ["eISSN", "E-ISSN", "Electronic ISSN"],
    "name": ["Name", "Journal name", "Journal Name", "Title"],
    "publisher": ["Publisher"],
    "jif": ["Journal Impact Factor", "JIF", "2025 JIF", "Impact Factor"],
    "jif_quartile": ["JIF quartile", "JIF Quartile"],
    "type": ["Type", "Edition"],
}
_WOS_REQUIRED = ["jif"]


def load_wos(path, metric_year=2025, sheet="Journals"):
    """Web of Science master -> Journal Impact Factor, JIF quartile, index type."""
    try:
        df = pd.read_excel(path, sheet_name=sheet)
    except ValueError:
        # the sheet may be named differently in a re-issued file
        df = pd.read_excel(path, sheet_name=0)

    cm = ColumnMap(df, _WOS_SPEC, _WOS_REQUIRED, source="Web of Science master")
    _require_any_issn(cm, "Web of Science master")

    with engine.begin() as conn:
        reg = JournalRegistry(conn)
        rows = []
        for _, r in df.iterrows():
            issns = split_issns(cm.get(r, "issn"))
            if not issns:
                issns = split_issns(cm.get(r, "print_issn")) + split_issns(
                    cm.get(r, "e_issn")
                )
            jid = reg.resolve(
                issns, title=cm.get(r, "name"), publisher=cm.get(r, "publisher"),
                authoritative=True,
            )
            if not jid:
                continue
            rows.append(
                {
                    "journal_id": jid,
                    "metric_year": metric_year,
                    "impact_factor": to_float(cm.get(r, "jif")),
                    "jif_quartile": norm_quartile(cm.get(r, "jif_quartile")),
                    "wos_type": clean_str(cm.get(r, "type"), 16),
                }
            )
        _upsert_metric(conn, rows, ["impact_factor", "jif_quartile", "wos_type"])

    return {"journals": len(rows), "metric_year": metric_year, **cm.report()}
