import shutil
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from loancopilot.auth import DB, CurrentUser, allowed_case_ids, get_case
from loancopilot.config import get_settings
from loancopilot.models import AiRun, Case, Company, Memo, User
from loancopilot.sectors import sector_group

router = APIRouter(prefix="/cases", tags=["cases"])

LegalForm = Literal["bv", "eenmanszaak", "vof", "other"]
Purpose = Literal["working_capital", "equipment", "real_estate", "refinancing", "growth", "other"]
Status = Literal["intake", "analysing", "waiting_review", "ready", "closed"]
OPEN_STATUSES = ("intake", "analysing", "waiting_review")


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    kvk_number: str | None = Field(default=None, pattern=r"^\d{8}$")
    legal_form: LegalForm
    sbi_code: str | None = Field(default=None, pattern=r"^\d{2,5}$")
    founded_year: int | None = Field(default=None, ge=1850, le=2100)
    employees: int | None = Field(default=None, ge=0)
    city: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CompanyOut(CompanyIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sector_group: str | None


class CaseCreate(BaseModel):
    company: CompanyIn
    loan_amount: Decimal = Field(gt=0, le=100_000_000)
    loan_purpose: Purpose
    loan_term_months: int = Field(ge=1, le=360)
    notes: str | None = None
    applied_on: date | None = None
    advisor_id: uuid.UUID | None = None


class CaseUpdate(BaseModel):
    status: Status | None = None
    notes: str | None = None
    loan_amount: Decimal | None = Field(default=None, gt=0, le=100_000_000)
    loan_purpose: Purpose | None = None
    loan_term_months: int | None = Field(default=None, ge=1, le=360)
    advisor_id: uuid.UUID | None = None


class AdvisorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class CaseOut(BaseModel):
    id: uuid.UUID
    status: str
    loan_amount: Decimal
    loan_purpose: str
    loan_term_months: int
    notes: str | None
    applied_on: date
    created_at: datetime
    updated_at: datetime
    company: CompanyOut
    advisor: AdvisorOut | None


class Stats(BaseModel):
    open_cases: int
    waiting_review: int
    memos_approved_this_month: int
    avg_days_to_ready: float | None


class CaseList(BaseModel):
    items: list[CaseOut]
    stats: Stats


def _out(case: Case, company: Company, advisor: User | None) -> CaseOut:
    return CaseOut(
        id=case.id, status=case.status, loan_amount=case.loan_amount,
        loan_purpose=case.loan_purpose, loan_term_months=case.loan_term_months,
        notes=case.notes, applied_on=case.applied_on, created_at=case.created_at,
        updated_at=case.updated_at, company=CompanyOut.model_validate(company),
        advisor=AdvisorOut.model_validate(advisor) if advisor else None,
    )  # fmt: skip


def _load(db: DB, case: Case) -> CaseOut:
    advisor = db.get(User, case.advisor_id) if case.advisor_id else None
    return _out(case, db.get_one(Company, case.company_id), advisor)


def _stats(db: DB, user: User) -> Stats:
    allowed = allowed_case_ids(user)
    count_status = select(func.count()).where(Case.id.in_(allowed))
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved = select(Memo).where(Memo.case_id.in_(allowed), Memo.status == "approved")
    avg_days = db.scalar(
        select(func.avg(func.extract("epoch", Memo.approved_at - Case.created_at) / 86400))
        .join(Case, Case.id == Memo.case_id)
        .where(Memo.case_id.in_(allowed), Memo.status == "approved")
    )
    return Stats(
        open_cases=db.scalar(count_status.where(Case.status.in_(OPEN_STATUSES))) or 0,
        waiting_review=db.scalar(count_status.where(Case.status == "waiting_review")) or 0,
        memos_approved_this_month=db.scalar(
            select(func.count()).select_from(
                approved.where(Memo.approved_at >= month_start).subquery()
            )
        )
        or 0,
        avg_days_to_ready=round(float(avg_days), 1) if avg_days is not None else None,
    )


@router.get("")
def list_cases(db: DB, user: CurrentUser, q: str | None = None,
               status: Status | None = None) -> CaseList:  # fmt: skip
    query = (
        select(Case, Company, User)
        .join(Company, Company.id == Case.company_id)
        .outerjoin(User, User.id == Case.advisor_id)
        .where(Case.id.in_(allowed_case_ids(user)))
        .order_by(Case.updated_at.desc())
    )
    if q:
        query = query.where(Company.name.ilike(f"%{q.strip()}%"))
    if status:
        query = query.where(Case.status == status)
    items = [_out(case, company, advisor) for case, company, advisor in db.execute(query)]
    return CaseList(items=items, stats=_stats(db, user))


def _check_advisor(db: DB, advisor_id: uuid.UUID) -> None:
    advisor = db.get(User, advisor_id)
    if advisor is None:
        raise HTTPException(422, "Advisor not found")


@router.post("", status_code=201)
def create_case(body: CaseCreate, db: DB, user: CurrentUser) -> CaseOut:
    advisor_id = user.id
    if body.advisor_id and user.role == "admin":
        _check_advisor(db, body.advisor_id)
        advisor_id = body.advisor_id
    company = Company(**body.company.model_dump(), sector_group=sector_group(body.company.sbi_code))
    db.add(company)
    db.flush()
    case = Case(
        company_id=company.id, advisor_id=advisor_id, loan_amount=body.loan_amount,
        loan_purpose=body.loan_purpose, loan_term_months=body.loan_term_months,
        notes=body.notes, applied_on=body.applied_on or date.today(),
    )  # fmt: skip
    db.add(case)
    db.commit()
    return _load(db, case)


@router.get("/{case_id}")
def read_case(case_id: uuid.UUID, db: DB, user: CurrentUser) -> CaseOut:
    return _load(db, get_case(db, user, case_id))


@router.patch("/{case_id}")
def update_case(case_id: uuid.UUID, body: CaseUpdate, db: DB, user: CurrentUser) -> CaseOut:
    case = get_case(db, user, case_id)
    changes = body.model_dump(exclude_unset=True)
    if "advisor_id" in changes:
        if user.role != "admin":
            raise HTTPException(403, "Only admins can reassign cases")
        _check_advisor(db, changes["advisor_id"])
    for field, value in changes.items():
        setattr(case, field, value)
    db.commit()
    return _load(db, case)


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    """Right to erasure: files and every case-linked row go; ai_runs keep metadata only."""
    case = get_case(db, user, case_id)
    db.execute(update(AiRun).where(AiRun.case_id == case.id).values(output_text=None))
    company = db.get_one(Company, case.company_id)
    db.delete(company)  # cascades to the case and every table that references it
    db.commit()
    shutil.rmtree(get_settings().data_dir / "files" / str(case_id), ignore_errors=True)
