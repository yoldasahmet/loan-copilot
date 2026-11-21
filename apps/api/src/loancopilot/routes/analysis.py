import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from loancopilot.analysis import compute, run_analysis
from loancopilot.auth import DB, CurrentUser, get_case
from loancopilot.db import SessionLocal
from loancopilot.extraction import FIELDS
from loancopilot.models import Analysis, Financial, User

router = APIRouter(tags=["analysis"])
log = logging.getLogger(__name__)
_running: set[uuid.UUID] = set()  # in-process background runs (see ADR 0006)


class FinancialOut(BaseModel):
    year: int
    values: dict[str, float | None]
    sources: dict[str, Any]
    warnings: list[dict]
    unit: str | None
    edited_fields: list[str]
    edited_by: str | None
    edited_at: datetime | None


class AnalysisOut(BaseModel):
    running: bool
    computed_at: datetime | None
    financials: list[FinancialOut]
    ratios: dict[str, Any] | None
    cashflow: dict[str, Any] | None
    red_flags: list[dict]
    missing_documents: list[dict]


class FinancialEdit(BaseModel):
    values: dict[str, float | None]


def _financial_out(db: DB, row: Financial) -> FinancialOut:
    editor = db.get(User, row.edited_by) if row.edited_by else None
    return FinancialOut(
        year=row.year,
        values={f: (float(v) if (v := getattr(row, f)) is not None else None) for f in FIELDS},
        sources={k: v for k, v in row.sources.items() if not k.startswith("_")},
        warnings=row.warnings, unit=row.sources.get("_unit"),
        edited_fields=row.sources.get("_edited", []),
        edited_by=editor.name if editor else None, edited_at=row.edited_at,
    )  # fmt: skip


def _analysis_out(db: DB, case_id: uuid.UUID) -> AnalysisOut:
    financials = db.scalars(
        select(Financial).where(Financial.case_id == case_id).order_by(Financial.year)
    )
    analysis = db.get(Analysis, case_id)
    return AnalysisOut(
        running=case_id in _running,
        computed_at=analysis.computed_at if analysis else None,
        financials=[_financial_out(db, f) for f in financials],
        ratios=analysis.ratios if analysis else None,
        cashflow=(analysis.cashflow or None) if analysis else None,
        red_flags=analysis.red_flags if analysis else [],
        missing_documents=analysis.missing_documents if analysis else [],
    )


def _run(case_id: uuid.UUID) -> None:
    try:
        with SessionLocal() as db:
            run_analysis(db, case_id)
    except Exception:
        log.exception("Analysis failed for case %s", case_id)
    finally:
        _running.discard(case_id)


@router.get("/cases/{case_id}/analysis")
def read_analysis(case_id: uuid.UUID, db: DB, user: CurrentUser) -> AnalysisOut:
    return _analysis_out(db, get_case(db, user, case_id).id)


@router.post("/cases/{case_id}/analysis/run", status_code=202)
def start_analysis(case_id: uuid.UUID, db: DB, user: CurrentUser,
                   background: BackgroundTasks) -> AnalysisOut:  # fmt: skip
    case = get_case(db, user, case_id)
    if case.id not in _running:
        _running.add(case.id)
        background.add_task(_run, case.id)
    return _analysis_out(db, case.id)


@router.patch("/cases/{case_id}/financials/{year}")
def edit_financials(case_id: uuid.UUID, year: int, body: FinancialEdit, db: DB,
                    user: CurrentUser) -> AnalysisOut:  # fmt: skip
    case = get_case(db, user, case_id)
    unknown = set(body.values) - set(FIELDS)
    if unknown:
        raise HTTPException(422, f"Unknown fields: {', '.join(sorted(unknown))}")
    row = db.scalar(select(Financial).where(Financial.case_id == case.id, Financial.year == year))
    if row is None:
        row = Financial(case_id=case.id, year=year, sources={}, warnings=[])
        db.add(row)
    for field, value in body.values.items():
        setattr(row, field, value)
    edited = sorted(set(row.sources.get("_edited", [])) | set(body.values))
    row.sources = {**row.sources, "_edited": edited}
    row.warnings = [w for w in row.warnings if w["field"] not in body.values]
    row.edited_by, row.edited_at = user.id, datetime.now(UTC)
    db.flush()
    compute(db, case)
    db.commit()
    return _analysis_out(db, case.id)
