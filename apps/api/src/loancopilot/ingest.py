"""Background ingestion: uploaded → parsing → indexed | failed."""

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from loancopilot.chunking import chunk_blocks, context_header
from loancopilot.config import get_settings
from loancopilot.db import SessionLocal
from loancopilot.embeddings import embed, model_name
from loancopilot.ingest_pdf import ParseError, parse_pdf
from loancopilot.ingest_statements import StatementError, parse_camt053, parse_csv
from loancopilot.models import Case, Chunk, Company, Document, Lender, Transaction
from loancopilot.security import MIME, injection_matches

log = logging.getLogger(__name__)


def file_path(doc: Document) -> Path:
    """Where an uploaded file lives: DATA_DIR/files/{case_id|lenders/id}/{sha256}.{ext}."""
    owner = str(doc.case_id) if doc.case_id else f"lenders/{doc.lender_id}"
    ext = next(e for e, m in MIME.items() if m == doc.mime)
    return get_settings().data_dir / "files" / owner / f"{doc.sha256}.{ext}"


def document_label(doc: Document, lender_name: str | None = None) -> str:
    if doc.kind == "annual_report":
        return f"Annual report {doc.year}" if doc.year else "Annual report"
    if doc.kind == "lender_criteria":
        return f"Lending criteria {lender_name}" if lender_name else "Lending criteria"
    if doc.kind == "bank_statement":
        return "Bank statement"
    return doc.filename


def _ingest_pdf(db: Session, doc: Document) -> None:
    parsed = parse_pdf(file_path(doc))
    doc.page_count = parsed.page_count
    company = lender = None
    if doc.case_id:
        case = db.get_one(Case, doc.case_id)
        company = db.get_one(Company, case.company_id).name
    if doc.lender_id:
        lender = db.get_one(Lender, doc.lender_id).name
    label = document_label(doc, lender)
    drafts = chunk_blocks(parsed.blocks)
    headers = [context_header(company or lender, label, d.section) for d in drafts]
    vectors = embed([f"{h}\n{d.text}" for h, d in zip(headers, drafts, strict=True)])
    # Flag text that looks like instructions to an AI; flagged chunks stay out of LLM context
    # until an advisor allows the document (the filter is in retrieval's SQL).
    doc.injection_flag = any(injection_matches(d.text) for d in drafts)
    doc.injection_allowed = False
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    for draft, header, vector in zip(drafts, headers, vectors, strict=True):
        db.add(Chunk(
            document_id=doc.id, case_id=doc.case_id, lender_id=doc.lender_id, kind=draft.kind,
            section=draft.section[:300] or None, page_from=draft.page_from, page_to=draft.page_to,
            text=draft.text, context_header=header, embedding=vector,
            embedding_model=model_name(),
        ))  # fmt: skip


def _ingest_statement(db: Session, doc: Document) -> None:
    if doc.case_id is None:
        raise StatementError("Bank statements belong to a case.")
    data = file_path(doc).read_bytes()
    parsed = parse_csv(data) if doc.mime == "text/csv" else parse_camt053(data)
    if not parsed:
        raise StatementError("The statement contains no transactions.")
    db.execute(delete(Transaction).where(Transaction.document_id == doc.id))
    db.add_all(
        Transaction(
            case_id=doc.case_id,
            document_id=doc.id,
            booked_on=t.booked_on,
            amount=t.amount,
            counterparty_name=t.counterparty_name,
            counterparty_iban=t.counterparty_iban,
            description=t.description,
            balance_after=t.balance_after,
        )  # fmt: skip
        for t in parsed
    )
    doc.year = max(t.booked_on for t in parsed).year


def ingest_document(document_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status, doc.error = "parsing", None
        db.commit()
        try:
            if doc.mime == "application/pdf":
                _ingest_pdf(db, doc)
            else:
                _ingest_statement(db, doc)
            doc.status = "indexed"
        except (ParseError, StatementError) as exc:
            db.rollback()
            doc.status, doc.error = "failed", str(exc)
        except Exception:
            log.exception("Ingestion failed for document %s", document_id)
            db.rollback()
            doc.status, doc.error = "failed", "This file could not be processed."
        db.commit()
