from datetime import date

from fastapi import APIRouter, Depends, Query

from ..config import CURRENT_METRIC_YEAR
from ..db import q
from ..deps import filter_params
from ..filters import BASE_FROM, PubFilters

router = APIRouter(prefix="/api", tags=["analytics"])


def _author_scope(f: PubFilters, alias="pa"):
    """Constrain the author row itself to the selected dimension.

    `PubFilters.where()` selects *publications* that have an author on the chosen
    campus/department -- correct for counting papers, wrong for counting people:
    without this, a department drill-down counts every co-author on that
    department's papers, including people from other departments and campuses.
    """
    own = ""
    if f.department_id:
        own += f" AND {alias}.department_id = :f_dept"
    if f.campus_id:
        own += f" AND {alias}.campus_id = :f_campus"
    if f.faculty_id:
        own += f" AND {alias}.faculty_id = :f_faculty"
    return own


def _scoped(f: PubFilters, select, extra_from="", group="", order="", limit=None):
    where, params = f.where()
    sql = f"SELECT {select} {BASE_FROM} {extra_from} WHERE {where} {group} {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return q(sql, **params)


# --------------------------------------------------------------- filter options

@router.get("/filters")
def filter_options():
    return {
        "campuses": q("SELECT id, name FROM campus ORDER BY name"),
        "departments": q(
            "SELECT d.id, d.name FROM department d ORDER BY d.name"
        ),
        "campus_departments": q(
            """SELECT DISTINCT f.campus_id, d.id AS department_id, d.name
               FROM faculty f JOIN department d ON d.id = f.department_id
               WHERE f.campus_id IS NOT NULL ORDER BY d.name"""
        ),
        "years": [
            r["year"]
            for r in q(
                "SELECT DISTINCT year FROM publication WHERE year IS NOT NULL "
                "AND is_bits = 1 ORDER BY year"
            )
        ],
        "document_types": [
            r["document_type"]
            for r in q(
                "SELECT document_type, COUNT(*) n FROM publication WHERE is_bits = 1 "
                "AND document_type IS NOT NULL GROUP BY document_type ORDER BY n DESC"
            )
        ],
        "quartiles": ["Q1", "Q2", "Q3", "Q4", "Unranked"],
        # the vintage the API actually computes on when the caller sends none --
        # the newest loaded vintage is not necessarily it
        "default_metric_year": CURRENT_METRIC_YEAR,
        "metric_years": [
            r["metric_year"]
            for r in q("SELECT DISTINCT metric_year FROM journal_metric ORDER BY metric_year DESC")
        ],
    }


# ------------------------------------------------------------------- executive

@router.get("/overview")
def overview(f: PubFilters = Depends(filter_params)):
    this_year = date.today().year
    row = _scoped(
        f,
        f"""COUNT(*)                                              AS total_publications,
            SUM(p.year = {this_year})                             AS publications_this_year,
            SUM(p.year = {this_year - 1})                         AS publications_last_year,
            COALESCE(SUM(p.cited_by), 0)                          AS total_citations,
            ROUND(AVG(p.cited_by), 2)                             AS avg_citations,
            COUNT(DISTINCT p.journal_id)                          AS total_journals,
            SUM(jm.sjr_quartile = 'Q1')                           AS q1_publications,
            SUM(jm.sjr_quartile = 'Q2')                           AS q2_publications,
            SUM(jm.sjr_quartile = 'Q3')                           AS q3_publications,
            SUM(jm.sjr_quartile = 'Q4')                           AS q4_publications,
            SUM(jm.impact_factor IS NOT NULL)                     AS publications_with_if,
            ROUND(AVG(jm.citescore), 2)                           AS avg_citescore,
            ROUND(AVG(jm.sjr), 3)                                 AS avg_sjr,
            ROUND(AVG(jm.impact_factor), 3)                       AS avg_impact_factor,
            SUM(p.is_open_access)                                 AS open_access_publications,
            SUM(p.faculty_matched = 0)                            AS unattributed_publications""",
    )[0]

    where, params = f.where()
    people = q(
        f"""SELECT COUNT(DISTINCT pa.faculty_id)    AS total_faculty_publishing,
                   COUNT(DISTINCT pa.department_id) AS total_departments,
                   COUNT(DISTINCT pa.campus_id)     AS total_campuses
            FROM publication_author pa
            JOIN publication p ON p.id = pa.publication_id
            LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                       AND jm.metric_year = :metric_year
            WHERE {where} AND pa.is_bits = 1 {_author_scope(f)}""",
        **params,
    )[0]

    out = {**row, **people}
    prev = out["publications_last_year"] or 0
    cur = out["publications_this_year"] or 0
    out["yoy_growth_pct"] = round((cur - prev) / prev * 100, 1) if prev else None
    return out


# ------------------------------------------------------------------- by year

@router.get("/analytics/by-year")
def by_year(f: PubFilters = Depends(filter_params)):
    rows = _scoped(
        f,
        """p.year,
           COUNT(*) AS publications,
           COALESCE(SUM(p.cited_by), 0) AS citations,
           SUM(jm.sjr_quartile = 'Q1') AS q1,
           SUM(jm.sjr_quartile = 'Q2') AS q2,
           SUM(jm.sjr_quartile = 'Q3') AS q3,
           SUM(jm.sjr_quartile = 'Q4') AS q4,
           ROUND(AVG(jm.citescore), 2) AS avg_citescore,
           ROUND(AVG(jm.sjr), 3) AS avg_sjr,
           ROUND(AVG(jm.impact_factor), 3) AS avg_impact_factor""",
        group="GROUP BY p.year HAVING p.year IS NOT NULL",
        order="ORDER BY p.year",
    )
    where, params = f.where()
    fac = {
        r["year"]: r["faculty"]
        for r in q(
            f"""SELECT p.year, COUNT(DISTINCT pa.faculty_id) AS faculty
                FROM publication_author pa
                JOIN publication p ON p.id = pa.publication_id
                LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                           AND jm.metric_year = :metric_year
                WHERE {where} AND pa.is_bits = 1 {_author_scope(f)}
                GROUP BY p.year""",
            **params,
        )
    }
    prev = None
    for r in rows:
        r["faculty"] = fac.get(r["year"], 0)
        r["growth_pct"] = (
            round((r["publications"] - prev) / prev * 100, 1) if prev else None
        )
        prev = r["publications"]
    return rows


@router.get("/analytics/citation-trend")
def citation_trend(f: PubFilters = Depends(filter_params)):
    """Total citations across the filtered corpus at each weekly upload, from the
    snapshot table -- this is the one series the raw Scopus file cannot give you."""
    where, params = f.where()
    return q(
        f"""SELECT pc.snapshot_date, SUM(pc.cited_by) AS citations,
                   COUNT(*) AS publications
            FROM publication_citation pc
            JOIN publication p ON p.id = pc.publication_id
            LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                       AND jm.metric_year = :metric_year
            WHERE {where}
            GROUP BY pc.snapshot_date ORDER BY pc.snapshot_date""",
        **params,
    )


@router.get("/analytics/by-document-type")
def by_document_type(f: PubFilters = Depends(filter_params)):
    return _scoped(
        f,
        """COALESCE(p.document_type, 'Unspecified') AS document_type,
           COUNT(*) AS publications, COALESCE(SUM(p.cited_by), 0) AS citations""",
        group="GROUP BY p.document_type",
        order="ORDER BY publications DESC",
    )


@router.get("/analytics/by-quartile")
def by_quartile(f: PubFilters = Depends(filter_params)):
    return _scoped(
        f,
        """COALESCE(jm.sjr_quartile, 'Unranked') AS quartile,
           COUNT(*) AS publications, COALESCE(SUM(p.cited_by), 0) AS citations""",
        group="GROUP BY quartile",
        order="ORDER BY quartile",
    )


@router.get("/analytics/by-open-access")
def by_open_access(f: PubFilters = Depends(filter_params)):
    return _scoped(
        f,
        """IF(p.is_open_access = 1, 'Open Access', 'Subscription') AS access,
           COUNT(*) AS publications, COALESCE(SUM(p.cited_by), 0) AS citations""",
        group="GROUP BY access",
        order="ORDER BY publications DESC",
    )


# ------------------------------------------------------- campus / department

def _group_by_author_dim(f: PubFilters, dim_table, dim_col):
    """Aggregate over a campus / department dimension.

    The (dimension, publication) pairs are made DISTINCT in a derived table
    before any SUM or AVG runs. Without that, a paper with three Pilani authors
    would join publication_author three times and triple its citation count.
    A Pilani+Goa paper still produces one pair per campus, which is exactly the
    agreed rule: full credit to each collaborating campus.
    """
    where, params = f.where()
    dedup = f"""
        SELECT DISTINCT pa.{dim_col} AS dim_id, pa.publication_id AS pub_id
        FROM publication_author pa
        JOIN publication p ON p.id = pa.publication_id
        LEFT JOIN journal j ON j.id = p.journal_id
        LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                   AND jm.metric_year = :metric_year
        WHERE {where} AND pa.is_bits = 1 AND pa.{dim_col} IS NOT NULL
    """
    rows = q(
        f"""SELECT dim.id, dim.name,
                   COUNT(*) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations,
                   SUM(jm.sjr_quartile = 'Q1') AS q1,
                   SUM(jm.sjr_quartile = 'Q2') AS q2,
                   SUM(jm.sjr_quartile = 'Q3') AS q3,
                   SUM(jm.sjr_quartile = 'Q4') AS q4,
                   SUM(jm.impact_factor IS NOT NULL) AS with_if,
                   SUM(p.is_open_access) AS open_access,
                   ROUND(AVG(jm.sjr), 3) AS avg_sjr,
                   ROUND(AVG(jm.citescore), 2) AS avg_citescore,
                   ROUND(AVG(jm.impact_factor), 3) AS avg_impact_factor
            FROM ({dedup}) dp
            JOIN {dim_table} dim ON dim.id = dp.dim_id
            JOIN publication p ON p.id = dp.pub_id
            LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                       AND jm.metric_year = :metric_year
            GROUP BY dim.id, dim.name
            ORDER BY publications DESC""",
        **params,
    )
    faculty = {
        r["dim_id"]: r["faculty"]
        for r in q(
            f"""SELECT pa.{dim_col} AS dim_id,
                       COUNT(DISTINCT pa.faculty_id) AS faculty
                FROM publication_author pa
                JOIN publication p ON p.id = pa.publication_id
                LEFT JOIN journal j ON j.id = p.journal_id
                LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                           AND jm.metric_year = :metric_year
                WHERE {where} AND pa.is_bits = 1 AND pa.{dim_col} IS NOT NULL
                GROUP BY pa.{dim_col}""",
            **params,
        )
    }
    for r in rows:
        r["faculty"] = faculty.get(r["id"], 0)
    return rows


@router.get("/analytics/by-campus")
def by_campus(f: PubFilters = Depends(filter_params)):
    return _group_by_author_dim(f, "campus", "campus_id")


@router.get("/analytics/by-department")
def by_department(f: PubFilters = Depends(filter_params)):
    return _group_by_author_dim(f, "department", "department_id")


# ------------------------------------------------------------------- top lists

@router.get("/analytics/top-journals")
def top_journals(f: PubFilters = Depends(filter_params), limit: int = Query(15)):
    return _scoped(
        f,
        """p.journal_id, COALESCE(j.title, p.source_title) AS journal,
           COUNT(*) AS publications, COALESCE(SUM(p.cited_by), 0) AS citations,
           MAX(jm.sjr_quartile) AS quartile, MAX(jm.citescore) AS citescore,
           MAX(jm.sjr) AS sjr, MAX(jm.impact_factor) AS impact_factor""",
        group="GROUP BY p.journal_id, journal",
        order="ORDER BY publications DESC, citations DESC",
        limit=limit,
    )


@router.get("/analytics/top-subjects")
def top_subjects(f: PubFilters = Depends(filter_params), limit: int = Query(15)):
    """Subject areas come from the CiteScore master's ASJC taxonomy -- the Scopus
    export itself carries no subject field."""
    where, params = f.where()
    return q(
        f"""SELECT js.subject, COUNT(DISTINCT p.id) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations
            FROM publication p
            JOIN journal_subject js ON js.journal_id = p.journal_id
                                   AND js.metric_year = :metric_year
            LEFT JOIN journal j ON j.id = p.journal_id
            LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                       AND jm.metric_year = :metric_year
            WHERE {where}
            GROUP BY js.subject ORDER BY publications DESC, citations DESC
            LIMIT {int(limit)}""",
        **params,
    )


@router.get("/analytics/top-faculty")
def top_faculty(f: PubFilters = Depends(filter_params), limit: int = Query(15)):
    """Top publishing faculty.

    When a campus or department is selected the faculty row itself is constrained
    too, not just the publication -- otherwise a department drill-down lists
    co-authors from other departments who happen to appear on its papers.
    """
    where, params = f.where()
    own = _author_scope(f, alias="fa")
    return q(
        f"""SELECT fa.id, fa.name, fa.designation, c.name AS campus, d.name AS department,
                   COUNT(DISTINCT p.id) AS publications,
                   COALESCE(SUM(p.cited_by), 0) AS citations,
                   COUNT(DISTINCT IF(jm.sjr_quartile = 'Q1', p.id, NULL)) AS q1
            FROM publication_author pa
            JOIN faculty fa ON fa.id = pa.faculty_id
            JOIN publication p ON p.id = pa.publication_id
            LEFT JOIN campus c ON c.id = fa.campus_id
            LEFT JOIN department d ON d.id = fa.department_id
            LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                                       AND jm.metric_year = :metric_year
            WHERE {where} {own}
            GROUP BY fa.id, fa.name, fa.designation, c.name, d.name
            ORDER BY publications DESC, citations DESC
            LIMIT {int(limit)}""",
        **params,
    )
