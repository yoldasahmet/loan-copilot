"""Historical cases: the pseudonymous import format, the import itself and case cards.

`python -m loancopilot.history` prints docs/import-format.md (make schema).
"""

import json
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loancopilot.embeddings import embed, model_name
from loancopilot.models import Analysis, Case, CaseCard, Company, Decision, Financial, Lender
from loancopilot.sectors import revenue_band, sector_group

LegalForm = Literal["bv", "eenmanszaak", "vof", "other"]
Purpose = Literal["working_capital", "equipment", "real_estate", "refinancing", "growth", "other"]
Money = Decimal

PURPOSE_TEXT = {
    "working_capital": "working capital", "equipment": "equipment", "real_estate": "real estate",
    "refinancing": "refinancing", "growth": "growth", "other": "other purposes",
}  # fmt: skip
FORM_TEXT = {"bv": "private limited company (BV)", "eenmanszaak": "sole proprietorship",
             "vof": "general partnership (VOF)", "other": "other legal form"}  # fmt: skip


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields (e.g. a name) are rejected


class HistoricalCompany(_Strict):
    legal_form: LegalForm
    sbi_code: str = Field(pattern=r"^\d{2,5}$", examples=["4322"])
    founded_year: int = Field(ge=1850, le=2100, examples=[2014])
    employees: int = Field(ge=0, examples=[25])
    region: str = Field(max_length=100, examples=["Overijssel"])


class HistoricalApplication(_Strict):
    applied_on: date = Field(examples=["2024-03-15"])
    amount: Money = Field(gt=0, examples=[250000])
    purpose: Purpose
    term_months: int = Field(ge=1, le=360, examples=[60])


class HistoricalFinancials(_Strict):
    year: int = Field(ge=1990, le=2100, examples=[2023])
    revenue: Money | None = Field(default=None, examples=[2500000])
    cost_of_sales: Money | None = None
    gross_profit: Money | None = None
    operating_expenses: Money | None = None
    ebitda: Money | None = None
    depreciation: Money | None = None
    interest_expense: Money | None = None
    net_income: Money | None = None
    total_assets: Money | None = None
    current_assets: Money | None = None
    cash: Money | None = None
    equity: Money | None = None
    current_liabilities: Money | None = None
    long_term_debt: Money | None = None


class CashflowSummary(_Strict):
    avg_monthly_inflow: Money = Field(ge=0, examples=[210000])
    negative_balance_days: int = Field(ge=0, le=366, examples=[0])
    top_customer_share: float = Field(ge=0, le=1, examples=[0.22])
    existing_annual_debt_service: Money = Field(ge=0, examples=[60000])


class HistoricalDecision(_Strict):
    lender_name: str = Field(min_length=1, examples=["Example Lender"])
    decision: Literal["approved", "declined", "withdrawn"]
    amount_granted: Money | None = Field(default=None, examples=[200000])
    interest_rate: float | None = Field(default=None, ge=0, le=1, examples=[0.072])
    term_months: int | None = Field(default=None, ge=1, le=360, examples=[60])
    decline_reason: str | None = Field(default=None, examples=[None])
    documents_requested: list[str] = Field(default_factory=list,
                                           examples=[["A cash-flow forecast"]])  # fmt: skip
    decided_on: date = Field(examples=["2024-04-02"])


class HistoricalCase(_Strict):
    """One historical case per JSONL line. There are no name fields: history is pseudonymous."""

    company: HistoricalCompany
    application: HistoricalApplication
    financials: list[HistoricalFinancials] = Field(min_length=1)
    cashflow_summary: CashflowSummary
    decisions: list[HistoricalDecision] = Field(min_length=1, max_length=10)


# ---------------------------------------------------------------- profile text (case cards)


def _eur(value: Decimal | float | None) -> str:
    if value is None:
        return "unknown"
    v = float(value)
    return f"€{v / 1_000_000:.1f} million" if abs(v) >= 1_000_000 else f"€{v / 1000:,.0f}k"


def profile_text(*, sector: str | None, legal_form: str, age: int | None,
                 financials: list[Financial], cashflow: dict | None, amount: Decimal,
                 purpose: str, term_months: int) -> str:  # fmt: skip
    """Profile fields only (never outcomes). Used for historical and open cases alike."""
    rows = sorted(financials, key=lambda f: f.year)
    lines = [
        f"Sector: {(sector or 'unknown').replace('_', ' ')}. "
        f"Legal form: {FORM_TEXT.get(legal_form, legal_form)}. "
        f"Company age: {age if age is not None else 'unknown'} years."
    ]
    if rows:
        fy = rows[-1]
        parts = [f"Revenue {_eur(fy.revenue)} in {fy.year}"]
        if len(rows) > 1 and rows[-2].revenue and fy.revenue is not None:
            growth = float(fy.revenue) / float(rows[-2].revenue) - 1
            parts.append(f"revenue growth {growth:+.0%}")
        if fy.ebitda is not None and fy.revenue:
            parts.append(f"EBITDA margin {float(fy.ebitda) / float(fy.revenue):.0%}")
        if fy.equity is not None and fy.total_assets:
            parts.append(f"solvency {float(fy.equity) / float(fy.total_assets):.0%}")
        lines.append(", ".join(parts) + ".")
    if cashflow:
        parts = [
            f"average monthly inflow {_eur(cashflow.get('avg_monthly_inflow'))}",
            f"{cashflow.get('negative_balance_days') or 0} days with a negative balance",
        ]
        if cashflow.get("top_customer_share") is not None:
            parts.append(f"largest customer {cashflow['top_customer_share']:.0%} of inflow")
        parts.append(
            f"existing annual debt service {_eur(cashflow.get('existing_annual_debt_service'))}"
        )
        lines.append("Cash flow: " + ", ".join(parts) + ".")
    lines.append(f"Loan request: {_eur(amount)} for {PURPOSE_TEXT.get(purpose, purpose)} over "
                 f"{term_months} months.")  # fmt: skip
    return "\n".join(lines)


def write_case_card(db: Session, case: Case, company: Company, financials: list[Financial],
                    cashflow: dict | None, first_decided_on: date | None) -> CaseCard:  # fmt: skip
    age = case.applied_on.year - company.founded_year if company.founded_year else None
    text = profile_text(sector=company.sector_group, legal_form=company.legal_form, age=age,
                        financials=financials, cashflow=cashflow, amount=case.loan_amount,
                        purpose=case.loan_purpose, term_months=case.loan_term_months)  # fmt: skip
    latest = max(financials, key=lambda f: f.year, default=None)
    card = db.get(CaseCard, case.id) or CaseCard(case_id=case.id)
    card.profile_text = text
    card.embedding = embed([text])[0]
    card.embedding_model = model_name()
    card.sector_group = company.sector_group
    card.revenue_band = revenue_band(latest.revenue if latest else None)
    card.loan_purpose = case.loan_purpose
    card.first_decided_on = first_decided_on
    db.add(card)
    return card


# ---------------------------------------------------------------- import


def _next_ref_number(db: Session) -> int:
    refs = db.scalars(select(Case.historical_ref).where(Case.historical_ref.is_not(None)))
    return max((int(r.split("-")[1]) for r in refs), default=0) + 1


def _import_one(db: Session, item: HistoricalCase, ref: str, lenders: dict[str, Lender]) -> None:
    c, a = item.company, item.application
    company = Company(name=None, legal_form=c.legal_form, sbi_code=c.sbi_code,
                      sector_group=sector_group(c.sbi_code), founded_year=c.founded_year,
                      employees=c.employees, city=c.region)  # fmt: skip
    db.add(company)
    db.flush()
    case = Case(company_id=company.id, advisor_id=None, status="closed", loan_amount=a.amount,
                loan_purpose=a.purpose, loan_term_months=a.term_months, is_historical=True,
                historical_ref=ref, applied_on=a.applied_on)  # fmt: skip
    db.add(case)
    db.flush()
    financials = [Financial(case_id=case.id, **f.model_dump()) for f in item.financials]
    db.add_all(financials)
    cashflow = item.cashflow_summary.model_dump(mode="json")
    db.add(Analysis(case_id=case.id, cashflow=cashflow))
    for d in item.decisions:
        db.add(Decision(case_id=case.id, lender_id=lenders[d.lender_name.lower()].id,
                        **d.model_dump(exclude={"lender_name"})))  # fmt: skip
    write_case_card(db, case, company, financials, cashflow,
                    min(d.decided_on for d in item.decisions))  # fmt: skip


def import_jsonl(db: Session, text: str) -> dict:
    """Validate every line; import the valid ones; report errors per line."""
    lenders = {lender.name.lower(): lender for lender in db.scalars(select(Lender))}
    errors: list[dict] = []
    valid: list[tuple[int, HistoricalCase]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = HistoricalCase.model_validate_json(line)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"]) or "line"
            errors.append({"line": number, "message": f"{where}: {first['msg']}"})
            continue
        unknown = sorted({d.lender_name for d in item.decisions if d.lender_name.lower()
                          not in lenders})  # fmt: skip
        if unknown:
            message = f"Unknown lender(s): {', '.join(unknown)}. Create them first."
            errors.append({"line": number, "message": message})
            continue
        valid.append((number, item))
    start = _next_ref_number(db)
    for offset, (_, item) in enumerate(valid):
        _import_one(db, item, f"H-{start + offset:04d}", lenders)
    db.commit()
    total = db.scalar(select(func.count()).select_from(Case).where(Case.is_historical.is_(True)))
    return {"imported": len(valid), "errors": errors, "total_historical": total or 0}


# ---------------------------------------------------------------- docs/import-format.md


def _type(prop: dict, defs: dict) -> str:
    """Readable type for one JSON Schema property."""
    if "anyOf" in prop:
        options = [p for p in prop["anyOf"] if p.get("type") != "null"]
        if any(p.get("type") == "number" for p in options):
            return "number"  # Decimal: a number or a numeric string
        return " or ".join(_type(p, defs) for p in options)
    if "enum" in prop:
        return "one of " + ", ".join(f"`{v}`" for v in prop["enum"])
    if "$ref" in prop:
        return "object"
    if prop.get("type") == "array":
        return f"list of {_type(prop['items'], defs)}s"
    if prop.get("format") == "date":
        return "date (YYYY-MM-DD)"
    return {"integer": "integer", "number": "number", "string": "text"}.get(prop.get("type"),
                                                                           "value")  # fmt: skip


def _rows(schema: dict, defs: dict, prefix: str = "") -> list[str]:
    rows = []
    required = set(schema.get("required", []))
    for name, prop in schema["properties"].items():
        ref = prop.get("$ref") or prop.get("items", {}).get("$ref")
        rows.append(f"| `{prefix}{name}` | {_type(prop, defs)} | "
                    f"{'yes' if name in required else 'no'} |")  # fmt: skip
        if ref:
            child = defs[ref.split("/")[-1]]
            rows += _rows(
                child, defs, f"{prefix}{name}{'[]' if prop.get('type') == 'array' else ''}."
            )
    return rows


EXAMPLE = {
    "company": {"legal_form": "bv", "sbi_code": "4322", "founded_year": 2014, "employees": 25,
                "region": "Overijssel"},
    "application": {"applied_on": "2024-03-15", "amount": 250000, "purpose": "equipment",
                    "term_months": 60},
    "financials": [{"year": 2023, "revenue": 2500000, "ebitda": 300000, "equity": 700000,
                    "total_assets": 1800000}],
    "cashflow_summary": {"avg_monthly_inflow": 210000, "negative_balance_days": 0,
                         "top_customer_share": 0.22, "existing_annual_debt_service": 60000},
    "decisions": [{"lender_name": "Example Lender", "decision": "approved",
                   "amount_granted": 200000, "interest_rate": 0.072, "term_months": 60,
                   "decline_reason": None, "documents_requested": ["A cash-flow forecast"],
                   "decided_on": "2024-04-02"}],
}  # fmt: skip


def import_format_markdown() -> str:
    schema_dict = HistoricalCase.model_json_schema()
    schema = json.dumps(schema_dict, indent=2)
    return "\n".join([
        "# Historical case import format",
        "",
        "<!-- Generated by `make schema` from `apps/api/src/loancopilot/history.py`. -->",
        "",
        "Upload a JSONL file (one JSON object per line) in **Admin → History import**. Each line",
        "is one past application with its lender decisions. The format has **no name fields**:",
        "historical cases are pseudonymous and get IDs like `H-0042`. Unknown fields are",
        "rejected, and every `lender_name` must match a lender created in the app.",
        "",
        "Outcomes (`decisions`) are never embedded; only the profile fields are used to find",
        "similar cases.",
        "",
        "## Fields",
        "",
        "| Field | Type | Required |",
        "|---|---|---|",
        *_rows(schema_dict, schema_dict["$defs"]),
        "",
        "Money is in EUR. `financials` holds one entry per year; any figure may be omitted.",
        "",
        "## Example line (placeholder values)",
        "",
        "```json",
        json.dumps(EXAMPLE),
        "```",
        "",
        "## JSON Schema",
        "",
        "```json",
        schema,
        "```",
        "",
    ])  # fmt: skip


if __name__ == "__main__":
    print(import_format_markdown(), end="")
