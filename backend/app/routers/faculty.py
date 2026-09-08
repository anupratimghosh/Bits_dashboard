from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import CURRENT_METRIC_YEAR
from ..db import q
from ..deps import filter_params
from ..filters import PubFilters, like

router = APIRouter(prefix="/api/faculty", tags=["faculty"])

SORTABLE = {
    "name": "fa.name",
    "publications": "publications",
    "citations": "citations",
    "q1": "q1",
    "campus": "campus",
    "department": "department",
    "avg_citescore": "avg_citescore",
    "avg_impact_factor": "avg_impact_factor",
}


@router.get("")
def list_faculty(
    f: PubFilters = Depends(filter_params),
    name: Optional[str] = Query(None),
    sort: str = Query("publications"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    publishing_only: bool = Query(True),
):
    """Faculty leaderboard. `publishing_only` keeps the 1,094-row IRINS roster
    from drowning the list; turn it off to include faculty with no publications
    under the current filter."""
    where, params = f.where()
    sort_col = SORTABLE.get(sort, "publications")
    direction = "ASC" if order.lower() == "asc" else "DESC"
    join = "JOIN" if publishing_only else "LEFT JOIN"

    extra = ""
    if name:
        extra += " AND fa.name LIKE :fname ESCAPE '!'"
        params["fname"] = like(name)
    if f.campus_id:
        extra += " AND fa.campus_id = :fac_campus"
        params["fac_campus"] = f.campus_id
    if f.department_id:
        extra += " AND fa.department_id = :fac_dept"
        params["fac_dept"] = f.department_id

    body = f"""
        FROM faculty fa
        LEFT JOIN campus c ON c.id = fa.campus_id
        LEFT JOIN department d ON d.id = fa.department_id
        {join} publication_author pa ON pa.faculty_id = fa.id
        {join} publication p ON p.id = pa.publication_id AND {where}
        LEFT JOIN journal j ON j.id = p.journal_id
        LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                   AND jm.metric_year = :metric_year
        WHERE 1 = 1 {extra}
    """
    rows = q(
        f"""SELECT fa.id, fa.name, fa.designation, fa.scopus_author_id,
                   c.name AS campus, d.name AS department,
                   COUNT(DISTINCT p.id) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations,
                   SUM(jm.sjr_quartile = 'Q1') AS q1,
                   SUM(jm.sjr_quartile = 'Q2') AS q2,
                   ROUND(AVG(jm.citescore), 2) AS avg_citescore,
                   ROUND(AVG(jm.impact_factor), 3) AS avg_impact_factor
            {body}
            GROUP BY fa.id, fa.name, fa.designation, fa.scopus_author_id,
                     c.name, d.name
            ORDER BY {sort_col} {direction}, fa.name ASC
            LIMIT :limit OFFSET :offset""",
        **params, limit=page_size, offset=(page - 1) * page_size,
    )
    total = q(
        f"SELECT COUNT(*) AS n FROM (SELECT fa.id {body} GROUP BY fa.id) t", **params
    )[0]["n"]
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/{faculty_id}")
def faculty_detail(faculty_id: int, metric_year: int = Query(CURRENT_METRIC_YEAR)):
    """Everything the dashboard shows when a professor is clicked."""
    prof = q(
        """SELECT fa.*, c.name AS campus, d.name AS department
           FROM faculty fa
           LEFT JOIN campus c ON c.id = fa.campus_id
           LEFT JOIN department d ON d.id = fa.department_id
           WHERE fa.id = :id""",
        id=faculty_id,
    )
    if not prof:
        raise HTTPException(404, "Faculty not found")
    prof = prof[0]

    base = """
        FROM publication_author pa
        JOIN publication p ON p.id = pa.publication_id
        LEFT JOIN journal j ON j.id = p.journal_id
        LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                   AND jm.metric_year = :my
        WHERE pa.faculty_id = :id
    """
    args = {"id": faculty_id, "my": metric_year}

    summary = q(
        f"""SELECT COUNT(*) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations,
                   ROUND(AVG(p.cited_by), 2) AS avg_citations,
                   MAX(p.cited_by) AS max_citations,
                   COUNT(DISTINCT p.journal_id) AS journals,
                   SUM(jm.sjr_quartile = 'Q1') AS q1,
                   SUM(jm.sjr_quartile = 'Q2') AS q2,
                   SUM(jm.sjr_quartile = 'Q3') AS q3,
                   SUM(jm.sjr_quartile = 'Q4') AS q4,
                   SUM(jm.impact_factor IS NOT NULL) AS with_if,
                   SUM(p.is_open_access) AS open_access,
                   ROUND(AVG(jm.citescore), 2) AS avg_citescore,
                   ROUND(AVG(jm.sjr), 3) AS avg_sjr,
                   ROUND(AVG(jm.impact_factor), 3) AS avg_impact_factor,
                   MIN(p.year) AS first_year, MAX(p.year) AS last_year
            {base}""",
        **args,
    )[0]

    # h-index computed over the publications actually held in this database --
    # labelled as such, since it is not the author's lifetime Scopus h-index.
    cites = [r["cited_by"] for r in q(f"SELECT p.cited_by {base} ORDER BY p.cited_by DESC", **args)]
    h = 0
    for i, c in enumerate(cites, start=1):
        if c >= i:
            h = i
        else:
            break
    summary["h_index_from_dataset"] = h
    summary["i10_index"] = sum(1 for c in cites if c >= 10)

    return {
        # the whole IRINS row, so the profile template can render every column
        # (expert_id, researcher_id, is_active ... ) instead of a chosen subset
        "faculty": prof,
        "summary": summary,
        "by_year": q(
            f"""SELECT p.year, COUNT(*) AS publications,
                       COALESCE(SUM(p.cited_by), 0) AS citations,
                       SUM(jm.sjr_quartile = 'Q1') AS q1
                {base} AND p.year IS NOT NULL
                GROUP BY p.year ORDER BY p.year""",
            **args,
        ),
        "quartiles": q(
            f"""SELECT COALESCE(jm.sjr_quartile, 'Unranked') AS quartile,
                       COUNT(*) AS publications
                {base} GROUP BY quartile ORDER BY quartile""",
            **args,
        ),
        "document_types": q(
            f"""SELECT COALESCE(p.document_type, 'Unspecified') AS document_type,
                       COUNT(*) AS publications
                {base} GROUP BY p.document_type ORDER BY publications DESC""",
            **args,
        ),
        "top_journals": q(
            f"""SELECT COALESCE(j.title, p.source_title) AS journal,
                       COUNT(*) AS publications,
                       COALESCE(SUM(p.cited_by), 0) AS citations,
                       MAX(jm.sjr_quartile) AS quartile,
                       MAX(jm.impact_factor) AS impact_factor
                {base} GROUP BY journal
                ORDER BY publications DESC, citations DESC LIMIT 10""",
            **args,
        ),
        "top_subjects": q(
            """SELECT js.subject, COUNT(DISTINCT p.id) AS publications
               FROM publication_author pa
               JOIN publication p ON p.id = pa.publication_id
               JOIN journal_subject js ON js.journal_id = p.journal_id
                                      AND js.metric_year = :my
               WHERE pa.faculty_id = :id
               GROUP BY js.subject ORDER BY publications DESC LIMIT 10""",
            **args,
        ),
        "collaborators": q(
            """SELECT f2.id, f2.name, c.name AS campus, d.name AS department,
                      COUNT(DISTINCT pa2.publication_id) AS joint_publications
               FROM publication_author pa1
               JOIN publication_author pa2
                 ON pa2.publication_id = pa1.publication_id
                AND pa2.faculty_id <> pa1.faculty_id
               JOIN faculty f2 ON f2.id = pa2.faculty_id
               LEFT JOIN campus c ON c.id = f2.campus_id
               LEFT JOIN department d ON d.id = f2.department_id
               WHERE pa1.faculty_id = :id
               GROUP BY f2.id, f2.name, c.name, d.name
               ORDER BY joint_publications DESC LIMIT 10""",
            id=faculty_id,
        ),
        "citation_trend": q(
            """SELECT pc.snapshot_date, SUM(pc.cited_by) AS citations
               FROM publication_citation pc
               JOIN publication_author pa ON pa.publication_id = pc.publication_id
               WHERE pa.faculty_id = :id
               GROUP BY pc.snapshot_date ORDER BY pc.snapshot_date""",
            id=faculty_id,
        ),
        "publications": q(
            f"""SELECT p.id, p.eid, p.title, p.year, p.document_type, p.doi, p.link,
                       p.cited_by, p.is_open_access, pa.author_seq,
                       COALESCE(j.title, p.source_title) AS journal,
                       jm.sjr_quartile AS quartile, jm.citescore, jm.sjr,
                       jm.impact_factor, jm.h_index AS journal_h_index
                {base}
                ORDER BY p.year DESC, p.cited_by DESC""",
            **args,
        ),
    }
