"""Similar cases and lender matching for an open case (cached on the analysis row)."""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from loancopilot.auth import DB, CurrentUser, get_case
from loancopilot.lenders import match_lenders
from loancopilot.models import Analysis
from loancopilot.similar import similar_cases

router = APIRouter(tags=["matching"])


class LenderMatches(BaseModel):
    lenders: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    similar_count: int
    errors: list[str]


@router.get("/cases/{case_id}/similar")
def read_similar(case_id: uuid.UUID, db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    case = get_case(db, user, case_id)
    analysis = db.get(Analysis, case.id)
    if analysis is not None and analysis.similar is not None:
        return analysis.similar
    result = similar_cases(db, case)
    if analysis is not None:
        analysis.similar = result
        db.commit()
    return result


@router.get("/cases/{case_id}/lenders")
def read_lenders(case_id: uuid.UUID, db: DB, user: CurrentUser) -> LenderMatches:
    case = get_case(db, user, case_id)
    analysis = db.get(Analysis, case.id)
    if analysis is not None and analysis.lender_matches is not None:
        return LenderMatches(**analysis.lender_matches)
    result = match_lenders(db, case)
    if analysis is not None and not result["errors"]:  # cache only complete results
        analysis.lender_matches = result
        db.commit()
    return LenderMatches(**result)
