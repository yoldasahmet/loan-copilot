from sqlalchemy import func, select

from loancopilot.db import SessionLocal
from loancopilot.models import Chunk, Transaction
from tests.factories import MINIMAL_PDF, new_case, upload

CSV = (
    b"date,amount,counterparty_name,counterparty_iban,description,balance\n"
    b"2026-01-05,250.50,Klant Een B.V.,,Invoice 1,1250.50\n"
    b"2026-03-28,-1500.00,Belastingdienst,,Payroll tax,-249.50\n"
)


def _count(model, **where) -> int:  # noqa: ANN001
    with SessionLocal() as db:
        query = select(func.count()).select_from(model)
        for key, value in where.items():
            query = query.where(getattr(model, key) == value)
        return db.scalar(query) or 0


def test_statement_upload_creates_transactions(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    doc = upload(a, case_id, "statements.csv", CSV).json()
    [listed] = a.get(f"/api/cases/{case_id}/documents").json()
    assert listed["status"] == "indexed" and listed["year"] == 2026
    assert _count(Transaction, document_id=doc["id"]) == 2


def test_pdf_upload_creates_chunks_with_pages_and_embeddings(login) -> None:
    a = login("advisor")
    case_id = new_case(a, "Testbouw B.V.")["id"]
    doc = upload(a, case_id, "annual_report_2025.pdf", MINIMAL_PDF).json()
    [listed] = a.get(f"/api/cases/{case_id}/documents").json()
    assert listed["status"] == "indexed" and listed["page_count"] == 3
    with SessionLocal() as db:
        chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc["id"])))
    assert {c.kind for c in chunks} == {"text", "table"}
    table = next(c for c in chunks if c.kind == "table")
    assert table.page_from == 3 and "Amounts in EUR" in table.section
    assert all(c.embedding is not None and c.embedding_model == "fake-hash-v1" for c in chunks)
    assert all(c.context_header.startswith("Company: Testbouw B.V. | Document: Annual report 2025")
               for c in chunks)  # fmt: skip


def test_reupload_same_file_does_nothing(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    upload(a, case_id, "statements.csv", CSV)
    upload(a, case_id, "statements-again.csv", CSV)
    assert len(a.get(f"/api/cases/{case_id}/documents").json()) == 1
    assert _count(Transaction) == 2


def test_broken_statement_fails_with_message(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    upload(a, case_id, "bad.csv", b"date,amount\n2026-01-01,1\n")
    [listed] = a.get(f"/api/cases/{case_id}/documents").json()
    assert listed["status"] == "failed"
    assert "missing columns" in listed["error"]


def test_scanned_pdf_fails(login, monkeypatch) -> None:
    from loancopilot import ingest
    from loancopilot.ingest_pdf import SCANNED_PDF_ERROR, ParseError

    def scanned(_path):  # noqa: ANN001, ANN202
        raise ParseError(SCANNED_PDF_ERROR)

    monkeypatch.setattr(ingest, "parse_pdf", scanned)
    a = login("advisor")
    case_id = new_case(a)["id"]
    upload(a, case_id, "scan.pdf", MINIMAL_PDF)
    [listed] = a.get(f"/api/cases/{case_id}/documents").json()
    assert listed["status"] == "failed" and listed["error"] == "Scanned PDFs are not supported."
