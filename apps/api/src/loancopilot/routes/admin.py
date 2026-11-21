import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from loancopilot.auth import DB, AdminUser, CurrentUser, hash_password
from loancopilot.history import import_jsonl
from loancopilot.ingest import ingest_document
from loancopilot.models import Document, Lender, User
from loancopilot.routes.documents import DocumentOut, store_document
from loancopilot.schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])

Role = Literal["admin", "advisor"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    role: Role = "advisor"
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


@router.get("/users")
def list_users(db: DB, admin: AdminUser) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in db.scalars(select(User).order_by(User.name))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: DB, admin: AdminUser) -> UserOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with this email already exists")
    user = User(name=body.name, email=email, role=body.role,
                password_hash=hash_password(body.password))  # fmt: skip
    db.add(user)
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DB, admin: AdminUser) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.role and user.id == admin.id and body.role != "admin":
        raise HTTPException(422, "You cannot remove your own admin role")
    if body.name:
        user.name = body.name
    if body.role:
        user.role = body.role
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    return UserOut.model_validate(user)


# ---------------------------------------------------------------- lenders

SectorGroup = Literal[
    "construction", "hospitality", "retail", "wholesale", "manufacturing",
    "transport_logistics", "it_services", "professional_services", "healthcare_practices",
    "agriculture",
]  # fmt: skip
LegalForm = Literal["bv", "eenmanszaak", "vof", "other"]


class LenderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_type: str = Field(min_length=1, max_length=40)
    min_amount: Decimal = Field(ge=0)
    max_amount: Decimal = Field(gt=0)
    min_revenue: Decimal = Field(ge=0)
    min_years_trading: int = Field(ge=0, le=100)
    excluded_sector_groups: list[SectorGroup] = []
    allowed_legal_forms: list[LegalForm] = ["bv", "eenmanszaak", "vof"]
    typical_rate_min: Decimal = Field(ge=0, le=1)
    typical_rate_max: Decimal = Field(ge=0, le=1)
    active: bool = True


class LenderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    product_type: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    min_revenue: Decimal | None = None
    min_years_trading: int | None = None
    excluded_sector_groups: list[SectorGroup] | None = None
    allowed_legal_forms: list[LegalForm] | None = None
    typical_rate_min: Decimal | None = None
    typical_rate_max: Decimal | None = None
    active: bool | None = None


class LenderOut(LenderIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    documents: list[DocumentOut] = []


def _lender_out(db: DB, lender: Lender) -> LenderOut:
    docs = db.scalars(select(Document).where(Document.lender_id == lender.id))
    out = LenderOut.model_validate(lender)
    out.documents = [DocumentOut.model_validate(d) for d in docs]
    return out


@router.get("/lenders")
def list_lenders(db: DB, user: CurrentUser) -> list[LenderOut]:
    """Lenders contain no personal data; every logged-in user may read them."""
    return [_lender_out(db, lender) for lender in db.scalars(select(Lender).order_by(Lender.name))]


@router.post("/lenders", status_code=201)
def create_lender(body: LenderIn, db: DB, admin: AdminUser) -> LenderOut:
    if db.scalar(select(Lender).where(Lender.name.ilike(body.name))):
        raise HTTPException(409, "A lender with this name already exists")
    if body.min_amount > body.max_amount or body.typical_rate_min > body.typical_rate_max:
        raise HTTPException(422, "Minimum values must not exceed maximum values")
    lender = Lender(**body.model_dump())
    db.add(lender)
    db.commit()
    return _lender_out(db, lender)


@router.patch("/lenders/{lender_id}")
def update_lender(lender_id: uuid.UUID, body: LenderUpdate, db: DB, admin: AdminUser) -> LenderOut:
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise HTTPException(404, "Lender not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(lender, field, value)
    db.commit()
    return _lender_out(db, lender)


@router.delete("/lenders/{lender_id}", status_code=204)
def delete_lender(lender_id: uuid.UUID, db: DB, admin: AdminUser) -> None:
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise HTTPException(404, "Lender not found")
    db.delete(lender)  # cascades to its decisions, criteria documents and chunks
    db.commit()


@router.post("/lenders/{lender_id}/documents", status_code=201)
async def upload_criteria(lender_id: uuid.UUID, db: DB, admin: AdminUser,
                          background: BackgroundTasks,
                          file: Annotated[UploadFile, File()]) -> DocumentOut:  # fmt: skip
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise HTTPException(404, "Lender not found")
    name = Path(file.filename or "criteria.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(422, "Lender criteria must be a PDF.")
    data = await file.read()
    doc, created = store_document(
        db, upload_name=name, data=data, kind="lender_criteria", year=None, lender_id=lender.id
    )
    if created:
        background.add_task(ingest_document, doc.id)
    return DocumentOut.model_validate(doc)


# ---------------------------------------------------------------- history import

MAX_HISTORY_BYTES = 20 * 1024 * 1024


class ImportResult(BaseModel):
    imported: int
    errors: list[dict]
    total_historical: int
    finished_at: datetime


@router.post("/history/import")
async def import_history(db: DB, admin: AdminUser,
                         file: Annotated[UploadFile, File()]) -> ImportResult:  # fmt: skip
    data = await file.read()
    if len(data) > MAX_HISTORY_BYTES:
        raise HTTPException(422, "History files may be at most 20 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "The file must be UTF-8 encoded JSONL.") from exc
    return ImportResult(**import_jsonl(db, text), finished_at=datetime.now().astimezone())
