from typing import Optional

from fastapi import Query

from .config import CURRENT_METRIC_YEAR
from .filters import PubFilters


def filter_params(
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    campus_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    faculty_id: Optional[int] = Query(None),
    document_type: Optional[str] = Query(None),
    quartile: Optional[str] = Query(None),
    open_access: Optional[bool] = Query(None),
    has_if: Optional[bool] = Query(None),
    subject: Optional[str] = Query(None),
    journal_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    matched_only: bool = Query(False),
    unmatched_only: bool = Query(False),
    metric_year: int = Query(CURRENT_METRIC_YEAR),
) -> PubFilters:
    return PubFilters(
        year_from=year_from, year_to=year_to, campus_id=campus_id,
        department_id=department_id, faculty_id=faculty_id,
        document_type=document_type, quartile=quartile, open_access=open_access,
        has_if=has_if, subject=subject, journal_id=journal_id, search=search,
        matched_only=matched_only, unmatched_only=unmatched_only,
        metric_year=metric_year,
    )
