"""One shared WHERE-clause builder for every analytics endpoint.

Campus and department filters go through EXISTS on publication_author, which is
what implements the agreed counting rule: a Goa-Hyderabad collaboration is one
publication that satisfies both the Goa filter and the Hyderabad filter, so it
counts once in each campus total and once in the institute total.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .config import CURRENT_METRIC_YEAR


def like(term: str) -> str:
    """Build a LIKE pattern that treats % and _ in the search box as literals.

    Without this, searching for "50%" matched "50" followed by anything, and a
    lone "%" matched the entire corpus. Pair with `ESCAPE '!'` in the SQL.
    """
    escaped = term.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


# Indian financial year: FY 2026 = 2026-27 = Apr 2026 .. Mar 2027, and
# Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar.
FY_SQL = "(YEAR(p.pub_date) - (MONTH(p.pub_date) < 4))"
FQ_SQL = "(((MONTH(p.pub_date) + 8) % 12) DIV 3 + 1)"


def fy_quarter_range(fy: int, fq: Optional[int] = None):
    """[start, end) dates of a financial year, or of one quarter of it."""
    if not fq:
        return date(fy, 4, 1), date(fy + 1, 4, 1)
    m = 3 + 3 * (fq - 1)          # months after 1 Jan of `fy`, 0-based
    start = date(fy + m // 12, m % 12 + 1, 1)
    m += 3
    return start, date(fy + m // 12, m % 12 + 1, 1)


def fy_label(fy: int) -> str:
    return f"{fy}-{(fy + 1) % 100:02d}"


@dataclass
class PubFilters:
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    fy: Optional[int] = None      # financial year (start year); needs a Crossref date
    fq: Optional[int] = None      # financial quarter 1-4
    campus_id: Optional[int] = None
    department_id: Optional[int] = None
    faculty_id: Optional[int] = None
    document_type: Optional[str] = None
    quartile: Optional[str] = None
    open_access: Optional[bool] = None
    has_if: Optional[bool] = None
    subject: Optional[str] = None
    journal_id: Optional[int] = None
    search: Optional[str] = None
    matched_only: bool = False
    unmatched_only: bool = False
    metric_year: int = field(default=CURRENT_METRIC_YEAR)

    def where(self):
        """Returns (sql, params). Assumes `publication p` and `journal_metric jm`
        are already in the FROM clause (see BASE_FROM)."""
        w = ["p.is_bits = 1"]
        p = {"metric_year": self.metric_year}

        if self.year_from is not None:
            w.append("p.year >= :year_from"); p["year_from"] = self.year_from
        if self.year_to is not None:
            w.append("p.year <= :year_to"); p["year_to"] = self.year_to
        # quarter filters can only match papers with a known date -- the UI
        # says so next to the dropdown
        if self.fy is not None:
            start, end = fy_quarter_range(self.fy, self.fq)
            w.append("p.pub_date >= :fy_start AND p.pub_date < :fy_end")
            p["fy_start"], p["fy_end"] = start, end
        elif self.fq:
            w.append(f"{FQ_SQL} = :fq"); p["fq"] = self.fq
        if self.document_type:
            w.append("p.document_type = :document_type")
            p["document_type"] = self.document_type
        if self.journal_id:
            w.append("p.journal_id = :journal_id"); p["journal_id"] = self.journal_id
        if self.open_access is not None:
            w.append("p.is_open_access = :oa"); p["oa"] = 1 if self.open_access else 0
        if self.matched_only:
            w.append("p.faculty_matched = 1")
        if self.unmatched_only:
            w.append("p.faculty_matched = 0")

        if self.quartile:
            if self.quartile.upper() == "UNRANKED":
                w.append("jm.sjr_quartile IS NULL")
            else:
                w.append("jm.sjr_quartile = :quartile")
                p["quartile"] = self.quartile.upper()
        if self.has_if is not None:
            # `is not None`, matching open_access: now that the frontend sends
            # booleans through, has_if=false must mean "no impact factor"
            # rather than silently disabling the filter
            w.append(
                "jm.impact_factor IS NOT NULL" if self.has_if
                else "jm.impact_factor IS NULL"
            )

        # author-scoped filters
        author_conds, ap = [], {}
        if self.campus_id:
            author_conds.append("pa.campus_id = :f_campus"); ap["f_campus"] = self.campus_id
        if self.department_id:
            author_conds.append("pa.department_id = :f_dept")
            ap["f_dept"] = self.department_id
        if self.faculty_id:
            author_conds.append("pa.faculty_id = :f_faculty")
            ap["f_faculty"] = self.faculty_id
        if author_conds:
            w.append(
                "EXISTS (SELECT 1 FROM publication_author pa WHERE "
                "pa.publication_id = p.id AND pa.is_bits = 1 AND "
                + " AND ".join(author_conds)
                + ")"
            )
            p.update(ap)

        if self.subject:
            w.append(
                "EXISTS (SELECT 1 FROM journal_subject js WHERE "
                "js.journal_id = p.journal_id AND js.metric_year = :metric_year "
                "AND js.subject = :subject)"
            )
            p["subject"] = self.subject

        if self.search:
            w.append(
                "(p.title LIKE :search ESCAPE '!' "
                "OR p.source_title LIKE :search ESCAPE '!' "
                "OR p.doi LIKE :search ESCAPE '!' "
                "OR EXISTS (SELECT 1 FROM publication_author pa2 "
                "WHERE pa2.publication_id = p.id "
                "AND pa2.full_name LIKE :search ESCAPE '!'))"
            )
            p["search"] = like(self.search)

        return " AND ".join(w), p


BASE_FROM = """
FROM publication p
LEFT JOIN journal j  ON j.id = p.journal_id
LEFT JOIN journal_metric jm ON jm.journal_id = p.journal_id
                           AND jm.metric_year = :metric_year
"""
