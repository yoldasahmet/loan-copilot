"""Annual-report figure extraction: the LLM reads the tables, code validates every figure."""

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from loancopilot import llm
from loancopilot.models import Case, Chunk, Company, Document, Financial
from loancopilot.security import Pseudonymiser

FIELDS = [
    "revenue", "cost_of_sales", "gross_profit", "operating_expenses", "ebitda", "depreciation",
    "interest_expense", "net_income", "total_assets", "current_assets", "cash", "equity",
    "current_liabilities", "long_term_debt",
]  # fmt: skip
TOLERANCE = Decimal("0.01")  # ±1% for the accounting identities

# No nullable types: structured outputs allow few union-typed fields, so "missing" is a flag.
_FIELD = {"type": "object", "properties": {"found": {"type": "boolean"},
                                            "value": {"type": "number"},
                                            "page": {"type": "integer"}}}  # fmt: skip
SCHEMA = llm.strict_schema({
    "type": "object",
    "properties": {
        "unit": {"type": "string", "enum": ["EUR", "EUR_thousands"]},
        "year": {"type": "integer"},
        "fields": {"type": "object", "properties": {f: _FIELD for f in FIELDS}},
    },
})  # fmt: skip

NUMBER_RE = re.compile(r"\(?[-−–]?\s?\d[\d.,]*\d\)?|\(?[-−–]?\d\)?")


def normalise_number(raw: str) -> Decimal | None:
    """'1.234.567', '1,234,567', '(12,345)', '−540', '12.5' → Decimal. Thousand separators are
    recognised by groups of exactly three digits."""
    s = raw.strip().replace(" ", "")
    negative = (s.startswith("(") and s.endswith(")")) or s[:1] in "-−–"
    s = s.strip("()").lstrip("-−–")
    if not s:
        return None
    if "," in s and "." in s:  # the last separator is the decimal mark
        decimal_mark = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal_mark == "," else ",", "").replace(decimal_mark, ".")
    else:
        for sep in (",", "."):
            if sep in s:
                parts = s.split(sep)
                thousands = len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3)
                s = s.replace(sep, "") if thousands else s.replace(sep, ".")
    try:
        value = Decimal(s)
    except ArithmeticError:
        return None
    return -value if negative else value


def numbers_in(text: str) -> set[Decimal]:
    out = set()
    for match in NUMBER_RE.finditer(text):
        value = normalise_number(match.group())
        if value is not None:
            out.add(abs(value))
    return out


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= max(abs(a), abs(b)) * TOLERANCE


def validate(
    values: dict[str, Decimal | None],
    displayed: dict[str, Decimal | None],
    pages: dict[str, int | None],
    page_text: dict[int, str],
) -> list[dict]:
    """Warnings for figures not found on their page and for failed accounting identities."""
    warnings: list[dict] = []

    def warn(field: str, message: str) -> None:
        warnings.append({"field": field, "message": message})

    page_numbers = {page: numbers_in(text) for page, text in page_text.items()}
    for field, shown in displayed.items():
        if shown is None:
            warn(field, "Not found in the report.")
        elif abs(shown) not in page_numbers.get(pages.get(field) or 0, set()):
            warn(field, f"The value {shown:,} was not found on page {pages.get(field)}.")

    v = values
    balance = ("total_assets", "equity", "long_term_debt", "current_liabilities")
    if all(v.get(f) is not None for f in balance):
        liabilities = v["equity"] + v["long_term_debt"] + v["current_liabilities"]
        if not _close(v["total_assets"], liabilities):
            warn(
                "total_assets",
                "Total assets do not equal equity + long-term debt + "
                f"current liabilities ({liabilities:,.0f}).",
            )
    if all(v.get(f) is not None for f in ("gross_profit", "revenue", "cost_of_sales")):
        expected = v["revenue"] - v["cost_of_sales"]
        if not _close(v["gross_profit"], expected):
            warn(
                "gross_profit",
                f"Gross profit does not equal revenue − cost of sales ({expected:,.0f}).",
            )
    return warnings


def _sources(chunks: list[Chunk]) -> str:
    return "\n\n".join(
        f'<source id="S{i}" page="{c.page_from}">\n{c.text}\n</source>'
        for i, c in enumerate(chunks, start=1)
    )


def extract_report(db: Session, doc: Document) -> Financial:
    """Extract one annual report into the financials row for its year (code validates)."""
    case = db.get_one(Case, doc.case_id)
    company = db.get_one(Company, case.company_id)
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id)
                             .order_by(Chunk.page_from)))  # fmt: skip
    tables = [c for c in chunks if c.kind == "table"] or chunks
    result = llm.complete(
        kind="extraction", prompt=llm.load_prompt("extraction"),
        user_content=f"Annual report {doc.year or ''}\n\n{_sources(tables)}",
        case_id=case.id, source_ids=[str(c.id) for c in tables], schema=SCHEMA, max_tokens=8000,
        pii=Pseudonymiser(company.name, [company.contact_name or ""]),
    )  # fmt: skip
    data: dict[str, Any] = result.data
    factor = Decimal(1000) if data["unit"] == "EUR_thousands" else Decimal(1)
    fields = data["fields"]
    displayed = {f: _decimal(fields[f]["value"]) if fields[f]["found"] else None for f in FIELDS}
    pages = {f: fields[f]["page"] if fields[f]["found"] else None for f in FIELDS}
    values = {f: (d * factor if d is not None else None) for f, d in displayed.items()}
    page_text: dict[int, str] = {}
    for c in chunks:
        for page in range(c.page_from or 1, (c.page_to or c.page_from or 1) + 1):
            page_text[page] = page_text.get(page, "") + "\n" + c.text
    year = doc.year or data["year"]
    row = db.scalar(select(Financial).where(Financial.case_id == case.id, Financial.year == year))
    if row is None:
        row = Financial(case_id=case.id, year=year)
        db.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    row.sources = {
        "_document_id": str(doc.id), "_unit": data["unit"],
        **{f: {"document_id": str(doc.id), "page": pages[f]} for f in FIELDS if pages[f]},
    }  # fmt: skip
    row.warnings = validate(values, displayed, pages, page_text)
    row.edited_by = row.edited_at = None
    db.flush()
    return row


def _decimal(value: float | int | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def unextracted_reports(db: Session, case_id: uuid.UUID) -> list[Document]:
    """Indexed annual reports that no financials row was extracted from yet."""
    done = {
        r.sources.get("_document_id")
        for r in db.scalars(select(Financial).where(Financial.case_id == case_id))
    }
    reports = db.scalars(select(Document).where(
        Document.case_id == case_id, Document.kind == "annual_report",
        Document.status == "indexed",
    ))  # fmt: skip
    return [d for d in reports if str(d.id) not in done]
