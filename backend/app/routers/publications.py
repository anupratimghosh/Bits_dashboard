from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import CURRENT_METRIC_YEAR
from ..db import q
from ..deps import filter_params
from ..filters import BASE_FROM, PubFilters

router = APIRouter(prefix="/api", tags=["publications"])

SORTABLE = {
    "title": "p.title",
    "year": "p.year",
    "cited_by": "p.cited_by",
    "journal": "journal",
    "quartile": "jm.sjr_quartile",
    "citescore": "jm.citescore",
    "sjr": "jm.sjr",
    "impact_factor": "jm.impact_factor",
    "document_type": "p.document_type",
}


@router.get("/publications")
def list_publications(
    f: PubFilters = Depends(filter_params),
    sort: str = Query("year"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
):
    where, params = f.where()
    sort_col = SORTABLE.get(sort, "p.year")
    direction = "ASC" if order.lower() == "asc" else "DESC"
    # NULL metrics always sort last regardless of direction, so an
    # impact-factor sort never opens on a page of blanks
    null_guard = f"({sort_col} IS NULL), " if sort_col.startswith("jm.") else ""

    rows = q(
        f"""SELECT p.id, p.eid, p.title, p.year, p.document_type, p.doi, p.link,
                   p.cited_by, p.is_open_access, p.faculty_matched,
                   COALESCE(j.title, p.source_title) AS journal,
                   jm.sjr_quartile AS quartile, jm.citescore, jm.sjr,
                   jm.snip, jm.impact_factor, jm.wos_type,
                   (SELECT GROUP_CONCAT(DISTINCT fa.name ORDER BY pa.author_seq
                                        SEPARATOR ', ')
                      FROM publication_author pa
                      JOIN faculty fa ON fa.id = pa.faculty_id
                     WHERE pa.publication_id = p.id) AS bits_authors,
                   (SELECT GROUP_CONCAT(DISTINCT c2.name ORDER BY c2.name
                                        SEPARATOR ', ')
                      FROM publication_author pa
                      JOIN campus c2 ON c2.id = pa.campus_id
                     WHERE pa.publication_id = p.id AND pa.is_bits = 1) AS campuses,
                   (SELECT GROUP_CONCAT(DISTINCT d2.name ORDER BY d2.name
                                        SEPARATOR ', ')
                      FROM publication_author pa
                      JOIN department d2 ON d2.id = pa.department_id
                     WHERE pa.publication_id = p.id AND pa.is_bits = 1) AS departments
            {BASE_FROM}
            WHERE {where}
            ORDER BY {null_guard}{sort_col} {direction}, p.id DESC
            LIMIT :limit OFFSET :offset""",
        **params, limit=page_size, offset=(page - 1) * page_size,
    )
    total = q(f"SELECT COUNT(*) AS n {BASE_FROM} WHERE {where}", **params)[0]["n"]
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/publications/{pub_id}")
def publication_detail(pub_id: int, metric_year: int = Query(CURRENT_METRIC_YEAR)):
    rows = q(
        """SELECT p.*, j.title AS journal_title, j.publisher AS journal_publisher,
                  j.issn_norm AS journal_issn, j.scopus_source_id,
                  jm.sjr, jm.sjr_quartile, jm.h_index, jm.citescore, jm.snip,
                  jm.cs_quartile, jm.cs_percentile, jm.impact_factor,
                  jm.jif_quartile, jm.wos_type,
                  jm.open_access AS journal_open_access,
                  b1.filename AS first_seen_file, b1.uploaded_at AS first_seen_at,
                  b2.filename AS last_batch_file, b2.uploaded_at AS last_batch_at
           FROM publication p
           LEFT JOIN journal j ON j.id = p.journal_id
           LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                      AND jm.metric_year = :my
           LEFT JOIN upload_batch b1 ON b1.id = p.first_seen_batch_id
           LEFT JOIN upload_batch b2 ON b2.id = p.last_batch_id
           WHERE p.id = :id""",
        id=pub_id, my=metric_year,
    )
    if not rows:
        raise HTTPException(404, "Publication not found")
    pub = rows[0]
    pub["authors"] = q(
        """SELECT pa.author_seq, pa.full_name, pa.raw_name, pa.scopus_author_id,
                  pa.raw_affiliation, pa.is_bits, pa.faculty_id,
                  fa.name AS faculty_name, c.name AS campus, d.name AS department
           FROM publication_author pa
           LEFT JOIN faculty fa ON fa.id = pa.faculty_id
           LEFT JOIN campus c ON c.id = pa.campus_id
           LEFT JOIN department d ON d.id = pa.department_id
           WHERE pa.publication_id = :id ORDER BY pa.author_seq""",
        id=pub_id,
    )
    pub["subjects"] = q(
        """SELECT js.subject, js.percentile, js.quartile
           FROM journal_subject js
           JOIN publication p ON p.journal_id = js.journal_id
           WHERE p.id = :id AND js.metric_year = :my
           ORDER BY js.percentile DESC""",
        id=pub_id, my=metric_year,
    )
    pub["citation_history"] = q(
        "SELECT snapshot_date, cited_by FROM publication_citation "
        "WHERE publication_id = :id ORDER BY snapshot_date",
        id=pub_id,
    )
    return pub


@router.get("/departments/{dept_id}")
def department_detail(dept_id: int, f: PubFilters = Depends(filter_params)):
    """Department drill-down: the same shape the campus page uses, scoped to one
    department (optionally within one campus via campus_id)."""
    f.department_id = dept_id
    where, params = f.where()
    dept = q("SELECT id, name FROM department WHERE id = :id", id=dept_id)
    if not dept:
        raise HTTPException(404, "Department not found")

    summary = q(
        f"""SELECT COUNT(*) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations,
                   COUNT(DISTINCT p.journal_id) AS journals,
                   SUM(jm.sjr_quartile = 'Q1') AS q1,
                   SUM(jm.sjr_quartile = 'Q2') AS q2,
                   SUM(jm.sjr_quartile = 'Q3') AS q3,
                   SUM(jm.sjr_quartile = 'Q4') AS q4,
                   SUM(jm.impact_factor IS NOT NULL) AS with_if,
                   SUM(p.is_open_access) AS open_access,
                   ROUND(AVG(jm.sjr), 3) AS avg_sjr,
                   ROUND(AVG(jm.citescore), 2) AS avg_citescore,
                   ROUND(AVG(jm.impact_factor), 3) AS avg_impact_factor
            {BASE_FROM} WHERE {where}""",
        **params,
    )[0]
    return {
        "department": dept[0],
        "summary": summary,
        "by_year": q(
            f"""SELECT p.year, COUNT(*) AS publications,
                       COALESCE(SUM(p.cited_by), 0) AS citations,
                       SUM(jm.sjr_quartile = 'Q1') AS q1
                {BASE_FROM} WHERE {where} AND p.year IS NOT NULL
                GROUP BY p.year ORDER BY p.year""",
            **params,
        ),
        "quartiles": q(
            f"""SELECT COALESCE(jm.sjr_quartile, 'Unranked') AS quartile,
                       COUNT(*) AS publications
                {BASE_FROM} WHERE {where} GROUP BY quartile ORDER BY quartile""",
            **params,
        ),
    }


@router.get("/journals/{journal_id}")
def journal_detail(journal_id: int, metric_year: int = Query(CURRENT_METRIC_YEAR)):
    rows = q(
        """SELECT j.*, jm.sjr, jm.sjr_quartile, jm.h_index, jm.citescore, jm.snip,
                  jm.impact_factor, jm.jif_quartile, jm.wos_type
           FROM journal j
           LEFT JOIN journal_metric jm ON jm.journal_id = j.id
                                      AND jm.metric_year = :my
           WHERE j.id = :id""",
        id=journal_id, my=metric_year,
    )
    if not rows:
        raise HTTPException(404, "Journal not found")
    j = rows[0]
    j["subjects"] = q(
        "SELECT subject, percentile, quartile FROM journal_subject "
        "WHERE journal_id = :id AND metric_year = :my ORDER BY percentile DESC",
        id=journal_id, my=metric_year,
    )
    return j
