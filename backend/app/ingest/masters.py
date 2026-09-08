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
    clean_str,
    norm_quartile,
    split_issns,
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


def load_irins(path, sheet=0):
    """IRINS faculty master -> campus, department, faculty."""
    df = pd.read_excel(path, sheet_name=sheet)
    cm = ColumnMap(df, _IRINS_SPEC, _IRINS_REQUIRED, source="IRINS master")

    with engine.begin() as conn:
        camp, dept = {}, {}
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "expert_id": to_int(cm.get(r, "expert_id")),
                    "sid": clean_str(cm.get(r, "scopus_id"), 32),
                    "name": clean_str(cm.get(r, "name"), 255) or "Unknown",
                    "title": clean_str(cm.get(r, "title"), 32),
                    "desig": clean_str(cm.get(r, "designation"), 96),
                    "email": clean_str(cm.get(r, "email"), 255),
                    "campus_id": _lookup_id(conn, "campus", cm.get(r, "campus"), camp),
                    "dept_id": _lookup_id(conn, "department", cm.get(r, "department"), dept),
                    "orcid": clean_str(cm.get(r, "orcid"), 64),
                    "rid": clean_str(cm.get(r, "researcher_id"), 64),
                    "gs": clean_str(cm.get(r, "gscholar"), 96),
                    "exp": clean_str(cm.get(r, "expertise")),
                    "qual": clean_str(cm.get(r, "qualification"), 128),
                    "active": 0 if clean_str(cm.get(r, "status")) == "I" else 1,
                }
            )
        # a Scopus ID must not land on two faculty rows -- keep the first
        seen, dupes = set(), 0
        for row in rows:
            if row["sid"] and row["sid"] in seen:
                row["sid"] = None
                dupes += 1
            elif row["sid"]:
                seen.add(row["sid"])

        # A Scopus ID reassigned to a different person would collide with the
        # UNIQUE key mid-upsert, so release every incoming ID from its current
        # owner first; the insert below then re-assigns them correctly.
        ids = list(seen)
        for i in range(0, len(ids), 1000):
            chunk = ids[i : i + 1000]
            binds = {f"i{k}": v for k, v in enumerate(chunk)}
            conn.execute(
                text(
                    "UPDATE faculty SET scopus_author_id = NULL "
                    f"WHERE scopus_author_id IN ({', '.join(':' + k for k in binds)})"
                ),
                binds,
            )

        _exec(
            conn,
            """INSERT INTO faculty
                 (expert_id, scopus_author_id, name, title, designation, email,
                  campus_id, department_id, orcid_id, researcher_id,
                  google_scholar_id, expertise, qualification, is_active)
               VALUES (:expert_id, :sid, :name, :title, :desig, :email,
                       :campus_id, :dept_id, :orcid, :rid, :gs, :exp, :qual, :active)
               ON DUPLICATE KEY UPDATE
                 scopus_author_id = VALUES(scopus_author_id), name = VALUES(name),
                 title = VALUES(title), designation = VALUES(designation),
                 email = VALUES(email), campus_id = VALUES(campus_id),
                 department_id = VALUES(department_id), orcid_id = VALUES(orcid_id),
                 researcher_id = VALUES(researcher_id),
                 google_scholar_id = VALUES(google_scholar_id),
                 expertise = VALUES(expertise), qualification = VALUES(qualification),
                 is_active = VALUES(is_active)""",
            rows,
        )

    out = {"faculty_rows": len(rows), "with_scopus_id": len(seen)}
    if dupes:
        out["duplicate_scopus_ids_dropped"] = dupes
    out.update(cm.report())
    return out


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
