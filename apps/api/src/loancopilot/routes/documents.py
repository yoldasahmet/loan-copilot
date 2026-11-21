import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select

from loancopilot.auth import DB, CurrentUser, allowed_case_ids, get_case
from loancopilot.config import get_settings
from loancopilot.models import Document
from loancopilot.security import MIME, UploadRejected, check_upload

router = APIRouter(tags=["documents"])

Kind = Literal["annual_report", "bank_statement", "lender_criteria", "other"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID | None
    lender_id: uuid.UUID | None
    kind: str
    filename: str
    mime: str
    size_bytes: int
    year: int | None
    page_count: int | None
    status: str
    error: str | None
    injection_flag: bool
    injection_allowed: bool
    created_at: datetime


def file_path(doc: Document) -> Path:
    owner = str(doc.case_id) if doc.case_id else f"lenders/{doc.lender_id}"
    ext = next(e for e, m in MIME.items() if m == doc.mime)
    return get_settings().data_dir / "files" / owner / f"{doc.sha256}.{ext}"


def store_document(db: DB, *, upload_name: str, data: bytes, kind: str, year: int | None,
                   case_id: uuid.UUID | None = None,
                   lender_id: uuid.UUID | None = None) -> tuple[Document, bool]:  # fmt: skip
    """Validate and store an upload. Returns (document, created); same file twice is a no-op."""
    try:
        ext = check_upload(upload_name, data)
    except UploadRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    sha = hashlib.sha256(data).hexdigest()
    owner = Document.case_id == case_id if case_id else Document.lender_id == lender_id
    existing = db.scalar(select(Document).where(owner, Document.sha256 == sha))
    if existing:
        return existing, False
    if year is None and (match := re.search(r"(20\d{2})", upload_name)):
        year = int(match.group(1))
    doc = Document(case_id=case_id, lender_id=lender_id, kind=kind, filename=upload_name,
                   sha256=sha, mime=MIME[ext], size_bytes=len(data), year=year)  # fmt: skip
    path = file_path(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    db.add(doc)
    db.commit()
    return doc, True


def _accessible_document(db: DB, user: CurrentUser, document_id: uuid.UUID) -> Document:
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            or_(Document.case_id.in_(allowed_case_ids(user)), Document.lender_id.is_not(None)),
        )
    )
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload_document(
    case_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    kind: Annotated[Kind | None, Form()] = None,
    year: Annotated[int | None, Form()] = None,
) -> DocumentOut:
    case = get_case(db, user, case_id)
    data = await file.read()
    name = Path(file.filename or "upload").name
    if kind is None:
        kind = "annual_report" if name.lower().endswith(".pdf") else "bank_statement"
    doc, _ = store_document(db, upload_name=name, data=data, kind=kind, year=year,
                            case_id=case.id)  # fmt: skip
    return DocumentOut.model_validate(doc)


@router.get("/cases/{case_id}/documents")
def list_documents(case_id: uuid.UUID, db: DB, user: CurrentUser) -> list[DocumentOut]:
    case = get_case(db, user, case_id)
    docs = db.scalars(
        select(Document).where(Document.case_id == case.id).order_by(Document.created_at)
    )
    return [DocumentOut.model_validate(d) for d in docs]


@router.get("/documents/{document_id}/file")
def download_document(document_id: uuid.UUID, db: DB, user: CurrentUser) -> FileResponse:
    doc = _accessible_document(db, user, document_id)
    inline = doc.mime == "application/pdf"
    return FileResponse(file_path(doc), media_type=doc.mime, filename=doc.filename,
                        content_disposition_type="inline" if inline else "attachment")  # fmt: skip


@router.post("/documents/{document_id}/allow")
def allow_document(document_id: uuid.UUID, db: DB, user: CurrentUser) -> DocumentOut:
    doc = _accessible_document(db, user, document_id)
    if doc.case_id is None and user.role != "admin":
        raise HTTPException(403, "Only admins can change lender documents")
    doc.injection_allowed = True
    db.commit()
    return DocumentOut.model_validate(doc)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    doc = _accessible_document(db, user, document_id)
    if doc.case_id is None and user.role != "admin":
        raise HTTPException(403, "Only admins can delete lender documents")
    path = file_path(doc)
    db.delete(doc)
    db.commit()
    path.unlink(missing_ok=True)
