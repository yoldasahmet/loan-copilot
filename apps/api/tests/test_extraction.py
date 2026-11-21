from decimal import Decimal

import pytest
from sqlalchemy import select

from loancopilot.db import SessionLocal
from loancopilot.extraction import FIELDS, normalise_number, numbers_in, validate
from loancopilot.models import AiRun, Case, Chunk, Document, Financial
from tests.factories import MINIMAL_PDF, new_case, upload


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.234.567", "1234567"), ("1,234,567", "1234567"), ("(12,345)", "-12345"),
     ("−540", "-540"), ("-1.234", "-1234"), ("12.5", "12.5"), ("1,800", "1800"),
     ("2.000.000", "2000000"), ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("900", "900")],
)  # fmt: skip
def test_normalise_number(raw: str, expected: str) -> None:
    assert normalise_number(raw) == Decimal(expected)


def test_numbers_in_table_text() -> None:
    text = "| Revenue | 1,800 | 1,620 |\n| Cost of sales | (540) | −486 |\n| Cash | 2.000.000 |"
    assert {Decimal(1800), Decimal(540), Decimal(486), Decimal(2_000_000)} <= numbers_in(text)


def _values(**overrides) -> dict:  # noqa: ANN003
    v = {f: Decimal(0) for f in FIELDS}
    v.update(total_assets=Decimal(900), equity=Decimal(405), long_term_debt=Decimal(80),
             current_liabilities=Decimal(415), revenue=Decimal(1800),
             cost_of_sales=Decimal(540), gross_profit=Decimal(1260))  # fmt: skip
    v.update({k: Decimal(str(x)) for k, x in overrides.items()})
    return v


def test_validate_page_check_and_identities() -> None:
    shown = {"revenue": Decimal(1800), "cash": Decimal(211)}
    pages = {"revenue": 4, "cash": 3}
    page_text = {3: "| Cash | 211 | 193 |", 4: "| Revenue | 1,800 | 1,620 |"}
    v = _values()
    assert validate(v, shown, pages, page_text) == []
    wrong_page = validate(v, {"cash": Decimal(211)}, {"cash": 4}, page_text)
    assert wrong_page[0]["field"] == "cash" and "page 4" in wrong_page[0]["message"]
    broken = validate(_values(total_assets=950, gross_profit=1300), {}, {}, page_text)
    assert {w["field"] for w in broken} == {"total_assets", "gross_profit"}
    within_1pct = validate(_values(total_assets=905), {}, {}, page_text)
    assert within_1pct == []


THOUSANDS_TABLE = (
    "Wessel IT B.V. — Balance sheet as at 31 December 2025 — Amounts in € thousands\n\n"
    "| | 31-12-2025 | 31-12-2024 |\n|---|---|---|\n| Cash | 211 | 193 |\n"
    "| Total assets | 900 | 830 |\n| Shareholders' equity | 405 | 349 |\n"
    "| Long-term liabilities | 80 | 100 |\n| Total current liabilities | 415 | 381 |"
)


def test_extract_report_converts_thousands_and_logs_the_run(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a, "Wessel IT B.V.")["id"]
    doc_id = upload(a, case_id, "annual_report_2025.pdf", MINIMAL_PDF).json()["id"]
    with SessionLocal() as db:  # replace the fake-parser chunks with a real-looking table
        db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
        db.add(Chunk(document_id=doc_id, case_id=case_id, kind="table", page_from=3, page_to=3,
                     text=THOUSANDS_TABLE, context_header="Company: Wessel IT B.V."))  # fmt: skip
        db.commit()
    fields = {f: {"value": None, "page": None} for f in FIELDS}
    fields.update(cash={"value": 211, "page": 3}, total_assets={"value": 900, "page": 3},
                  equity={"value": 405, "page": 3}, long_term_debt={"value": 80, "page": 3},
                  current_liabilities={"value": 415, "page": 3})  # fmt: skip
    fake_llm.queue({"unit": "EUR_thousands", "year": 2025, "fields": fields})

    from loancopilot.extraction import extract_report

    with SessionLocal() as db:
        row = extract_report(db, db.get_one(Document, doc_id))
        db.commit()
        assert row.total_assets == Decimal(900_000) and row.cash == Decimal(211_000)
        assert row.sources["_unit"] == "EUR_thousands"
        assert row.sources["cash"] == {"document_id": doc_id, "page": 3}
        flagged = {w["field"] for w in row.warnings}
        assert "total_assets" not in flagged and "cash" not in flagged  # found on page 3
        assert "revenue" in flagged  # null → "Not found in the report."
        run = db.scalar(select(AiRun).where(AiRun.kind == "extraction"))
        assert run.prompt_version == "extraction-v1" and run.input_tokens == 120
        assert run.model == "fake-model"
        assert run.cost_usd > 0 and str(run.case_id) == case_id
    sent = fake_llm.requests[0]
    assert "Wessel" not in sent.user and "[COMPANY]" in sent.user  # pseudonymised first
    assert sent.schema is not None and sent.schema["additionalProperties"] is False
    with SessionLocal() as db:
        assert db.scalar(select(Financial.year).where(Financial.case_id == case_id)) == 2025
        assert db.get(Case, case_id) is not None
