"""Financial analysis, all in code: categories, ratios, cash flow, red flags, missing documents."""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from loancopilot.chunking import context_header
from loancopilot.config import get_settings
from loancopilot.embeddings import embed, model_name
from loancopilot.extraction import extract_report, unextracted_reports
from loancopilot.llm import LlmError
from loancopilot.models import Analysis, Case, Chunk, Company, Document, Financial, Transaction
from loancopilot.similar import find_similar, precedent_document_requests

THRESHOLDS: dict[str, float] = {
    "solvency_min": 0.20,
    "current_ratio_min": 1.0,
    "revenue_growth_min": -0.15,
    "debt_ebitda_max": 4.0,
    "interest_coverage_min": 3.0,
    "dscr_min": 1.25,
    "negative_balance_days_max": 10,
    "top_customer_share_max": 0.40,
    "company_age_min_years": 3,
    "annual_reports_min": 2,
}
AMBER_BAND = 0.10  # within 10% of a threshold (on the safe side) shows amber

# Checked in order against "counterparty description" (lower case). Unmatched: incoming money
# is "customers", outgoing money to a named counterparty is "suppliers", the rest is "other".
CATEGORY_RULES: dict[str, list[str]] = {
    "tax": [r"belastingdienst", r"tax authority", r"\bvat\b", r"\bbtw\b", r"loonheffing"],
    "salaries": [r"salar", r"payroll", r"\bloon", r"wages"],
    "loan_repayment": [r"loan repayment", r"aflossing", r"\blening", r"loan instalment"],
    "rent": [r"\brent\b", r"\bhuur"],
    "bank_fees": [r"bank fees?", r"payment fees", r"bankkosten", r"account fee"],
}
CATEGORIES = [*CATEGORY_RULES, "customers", "suppliers", "other"]


def categorise(amount: Decimal, counterparty: str | None, description: str | None) -> str:
    text = f"{counterparty or ''} {description or ''}".lower()
    for category, patterns in CATEGORY_RULES.items():
        if any(re.search(p, text) for p in patterns):
            return category
    if amount > 0:
        return "customers"
    return "suppliers" if counterparty else "other"


# ---------------------------------------------------------------- ratios


def annuity_annual(principal: float, rate: float, months: int) -> float:
    """Annual debt service of an annuity loan (12 monthly payments)."""
    if months <= 0:
        return 0.0
    r = rate / 12
    monthly = principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)
    return monthly * 12


def _div(a: Decimal | float | None, b: Decimal | float | None) -> float | None:
    if a is None or b is None or float(b) == 0:
        return None
    return float(a) / float(b)


def format_ratio(value: float | None, kind: str, decimals: int = 1) -> str:
    """38.0% for percent ratios, 1.52x for multiples."""
    if value is None:
        return "n/a"
    return f"{value * 100:.{decimals}f}%" if kind == "percent" else f"{value:.2f}x"


def status(value: float | None, threshold: float | None, higher_is_better: bool) -> str:
    """green / amber / red against a threshold; neutral when there is no threshold or value."""
    if value is None or threshold is None:
        return "neutral"
    band = abs(threshold) * AMBER_BAND
    if higher_is_better:
        return "red" if value < threshold else "amber" if value < threshold + band else "green"
    return "red" if value > threshold else "amber" if value > threshold - band else "green"


@dataclass(frozen=True)
class RatioSpec:
    key: str
    label: str
    kind: str  # percent | multiple
    threshold_key: str | None
    higher_is_better: bool
    formula: str


RATIOS = [
    RatioSpec("solvency", "Solvency", "percent", "solvency_min", True, "equity / total assets"),
    RatioSpec("current_ratio", "Current ratio", "multiple", "current_ratio_min", True,
              "current assets / current liabilities"),
    RatioSpec("ebitda_margin", "EBITDA margin", "percent", None, True, "EBITDA / revenue"),
    RatioSpec("revenue_growth", "Revenue growth", "percent", "revenue_growth_min", True,
              "revenue / previous year's revenue − 1"),
    RatioSpec("debt_ebitda", "Debt / EBITDA", "multiple", "debt_ebitda_max", False,
              "long-term debt / EBITDA"),
    RatioSpec("interest_coverage", "Interest coverage", "multiple", "interest_coverage_min",
              True, "EBITDA / interest expense"),
    RatioSpec("dscr", "DSCR", "multiple", "dscr_min", True,
              "EBITDA / (existing + new annual debt service)"),
]  # fmt: skip


def _ratio_values(fy: Financial, prev: Financial | None, debt_service: float | None) -> dict:
    debt_ebitda = None
    if fy.ebitda is not None and fy.long_term_debt is not None:
        debt_ebitda = _div(fy.long_term_debt, fy.ebitda) if fy.ebitda > 0 else float("inf")
    growth = None
    if prev is not None and prev.revenue:
        growth = _div(fy.revenue, prev.revenue)
        growth = growth - 1 if growth is not None else None
    return {
        "solvency": _div(fy.equity, fy.total_assets),
        "current_ratio": _div(fy.current_assets, fy.current_liabilities),
        "ebitda_margin": _div(fy.ebitda, fy.revenue),
        "revenue_growth": growth,
        "debt_ebitda": debt_ebitda,
        "interest_coverage": _div(fy.ebitda, fy.interest_expense),
        "dscr": _div(fy.ebitda, debt_service) if debt_service else None,
    }


def compute_ratios(financials: list[Financial], loan_amount: float, term_months: int,
                   existing_debt_service: float | None) -> dict[str, Any]:  # fmt: skip
    """Ratios for the latest year, with the previous year alongside where available."""
    rate = get_settings().assumed_interest_rate
    new_ds = annuity_annual(loan_amount, rate, term_months)
    existing = existing_debt_service or 0.0
    assumptions = {
        "interest_rate": rate, "loan_amount": loan_amount, "term_months": term_months,
        "new_annual_debt_service": round(new_ds, 2),
        "existing_annual_debt_service": round(existing, 2),
        "existing_debt_service_from_statements": existing_debt_service is not None,
    }  # fmt: skip
    rows = sorted(financials, key=lambda f: f.year)
    if not rows:
        return {"year": None, "items": [], "assumptions": assumptions}
    latest = rows[-1]
    prev = rows[-2] if len(rows) > 1 and rows[-2].year == latest.year - 1 else None
    before = rows[-3] if len(rows) > 2 and rows[-3].year == latest.year - 2 else None
    current = _ratio_values(latest, prev, existing + new_ds)
    previous = _ratio_values(prev, before, None) if prev else {}
    items = []
    for spec in RATIOS:
        threshold = THRESHOLDS.get(spec.threshold_key) if spec.threshold_key else None
        value = current[spec.key]
        if value == float("inf"):
            value = None  # zero or negative EBITDA: debt/EBITDA is undefined (flagged as red)
            state = "red"
        else:
            state = status(value, threshold, spec.higher_is_better)
        items.append({
            "key": spec.key, "label": spec.label, "kind": spec.kind, "value": value,
            "previous": None if spec.key == "dscr" else previous.get(spec.key),
            "threshold": threshold, "higher_is_better": spec.higher_is_better,
            "status": state, "formula": spec.formula, "year": latest.year,
        })  # fmt: skip
    return {"year": latest.year, "items": items, "assumptions": assumptions}


# ---------------------------------------------------------------- cash flow


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _quarter_key(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def compute_cashflow(transactions: list[Transaction]) -> dict[str, Any] | None:
    """Monthly flows and metrics over the last 12 months of transactions."""
    if not transactions:
        return None
    txs = sorted(transactions, key=lambda t: t.booked_on)
    end = txs[-1].booked_on
    start_year, start_month = end.year, end.month - 11
    if start_month <= 0:
        start_year, start_month = start_year - 1, start_month + 12
    start = date(start_year, start_month, 1)
    window = [t for t in txs if t.booked_on >= start]
    months: dict[str, dict[str, Any]] = {}
    y, m = start.year, start.month
    for _ in range(12):
        months[f"{y}-{m:02d}"] = {"month": f"{y}-{m:02d}", "inflow": 0.0, "outflow": 0.0,
                                  "net": 0.0, "end_balance": None}  # fmt: skip
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    categories: dict[str, dict[str, float]] = {c: {"in": 0.0, "out": 0.0} for c in CATEGORIES}
    customers: dict[str, float] = defaultdict(float)
    quarters: dict[str, float] = {}
    for t in window:
        amount = float(t.amount)
        month = months[_month_key(t.booked_on)]
        if amount >= 0:
            month["inflow"] += amount
            categories[t.category]["in"] += amount
        else:
            month["outflow"] += -amount
            categories[t.category]["out"] += -amount
        month["net"] += amount
        if t.balance_after is not None:
            month["end_balance"] = float(t.balance_after)
        if t.category == "customers":
            customers[t.counterparty_name or "Unknown"] += amount
    d = start
    while d <= end:  # every quarter touched by the window, also those without tax payments
        quarters.setdefault(_quarter_key(d), 0.0)
        d += timedelta(days=28)
    quarters.setdefault(_quarter_key(end), 0.0)
    for t in window:
        if t.category == "tax" and t.amount < 0:
            quarters[_quarter_key(t.booked_on)] += -float(t.amount)

    total_in = sum(mo["inflow"] for mo in months.values())
    customer_total = sum(customers.values())
    top_name, top_amount = max(customers.items(), key=lambda kv: kv[1], default=(None, 0.0))
    debt_service = -sum(float(t.amount) for t in window if t.category == "loan_repayment")
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "covered_days": (end - txs[0].booked_on).days + 1,
        "months": [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in mo.items()}
            for mo in months.values()
        ],  # fmt: skip
        "avg_monthly_inflow": round(total_in / 12, 2),
        "months_negative_net": sum(1 for mo in months.values() if mo["net"] < 0),
        "negative_balance_days": _negative_balance_days(window, start, end),
        "top_customer": top_name,
        "top_customer_share": round(top_amount / customer_total, 4) if customer_total else None,
        "existing_annual_debt_service": round(debt_service, 2),
        "tax_per_quarter": [
            {"quarter": q, "amount": round(a, 2)} for q, a in sorted(quarters.items())
        ],  # fmt: skip
        "categories": [
            {"category": c, "in": round(v["in"], 2), "out": round(v["out"], 2)}
            for c, v in categories.items()
            if v["in"] or v["out"]
        ],  # fmt: skip
    }


def _negative_balance_days(window: list[Transaction], start: date, end: date) -> int | None:
    """Calendar days with a negative end-of-day balance (balance carried forward)."""
    if not window or any(t.balance_after is None for t in window):
        return None
    eod: dict[date, float] = {}
    for t in window:
        eod[t.booked_on] = float(t.balance_after)  # type: ignore[arg-type]
    first = window[0]
    balance = float(first.balance_after) - float(first.amount)  # type: ignore[arg-type]
    count, day = 0, start
    while day <= end:
        balance = eod.get(day, balance)
        count += balance < 0
        day += timedelta(days=1)
    return count


# ---------------------------------------------------------------- red flags, documents


def red_flags(ratios: dict, cashflow: dict | None, company: Company, applied_on: date,
              report_years: list[int]) -> list[dict]:  # fmt: skip
    t = THRESHOLDS
    flags: list[dict] = []

    def flag(code: str, title: str, detail: str, severity: str = "high") -> None:
        flags.append({"code": code, "title": title, "detail": detail, "severity": severity})

    for item in ratios["items"]:
        if item["status"] != "red":
            continue
        threshold, value = item["threshold"], item["value"]
        shown = format_ratio(value, item["kind"])
        limit = format_ratio(threshold, item["kind"], decimals=0)
        side = "below" if item["higher_is_better"] else "above"
        flag(
            item["key"],
            f"{item['label']} {side} threshold",
            f"{item['label']} is {shown} in {item['year']} ({side} the {limit} threshold).",
        )
    if cashflow:
        days = cashflow["negative_balance_days"]
        if days is not None and days > t["negative_balance_days_max"]:
            flag(
                "overdraft",
                "Frequent negative balance",
                f"The account balance was negative on {days} days in the last 12 months.",
            )
        share = cashflow["top_customer_share"]
        if share is not None and share > t["top_customer_share_max"]:
            flag(
                "customer_concentration",
                "Customer concentration",
                f"The largest customer accounts for {share:.0%} of customer inflow.",
            )
        missing = [q["quarter"] for q in cashflow["tax_per_quarter"] if q["amount"] == 0]
        if missing:
            flag(
                "tax_gap",
                "Quarter without tax payment",
                f"No payments to the tax authority in {', '.join(missing)}.",
            )
    if company.founded_year is not None:
        age = applied_on.year - company.founded_year
        if age < t["company_age_min_years"]:
            flag("young_company", "Young company", f"The company is {age} years old.", "medium")
    if len(set(report_years)) < t["annual_reports_min"]:
        flag(
            "few_reports",
            "Fewer than two annual reports",
            f"{len(set(report_years))} annual report(s) uploaded.",
            "medium",
        )
    return flags


def missing_documents(applied_on: date, report_years: list[int], cashflow: dict | None,
                      precedent_requests: list[dict] | None = None) -> list[dict]:  # fmt: skip
    """Base checklist plus documents lenders often requested in similar cases (≥30%)."""
    items = []
    for year in (applied_on.year - 1, applied_on.year - 2):
        items.append({"document": f"Annual report {year}", "present": year in report_years,
                      "reason": "Required for every application"})  # fmt: skip
    statements_ok = bool(
        cashflow and cashflow["covered_days"] >= 330
        and (applied_on - date.fromisoformat(cashflow["period_end"])).days <= 120
    )  # fmt: skip
    items.append({"document": "Bank statements for the last 12 months", "present": statements_ok,
                  "reason": "Required for every application"})  # fmt: skip
    for request in precedent_requests or []:
        items.append({"document": request["document"], "present": False,
                      "reason": f"Requested in {request['share']:.0%} of similar cases",
                      "share": request["share"]})  # fmt: skip
    return items


# ---------------------------------------------------------------- analysis chunk and run


def _eur(value: float | None) -> str:
    return "n/a" if value is None else f"€{value:,.0f}"


def analysis_text(company: str, ratios: dict, cashflow: dict | None, flags: list[dict]) -> str:
    lines = [f"Financial analysis of {company}, calculated in code from the extracted figures "
             "and bank transactions."]  # fmt: skip
    a = ratios["assumptions"]
    if ratios["items"]:
        lines.append(f"Ratios for {ratios['year']}:")
        for item in ratios["items"]:
            value = item["value"]
            shown = format_ratio(value, item["kind"])
            lines.append(f"- {item['label']}: {shown} ({item['formula']}; status {item['status']})")
        lines.append(
            f"DSCR assumptions: new loan {_eur(a['loan_amount'])} over {a['term_months']} months "
            f"at an assumed {a['interest_rate']:.1%} interest rate gives a new annual debt service "
            f"of {_eur(a['new_annual_debt_service'])}; existing annual debt service from the bank "
            f"statements is {_eur(a['existing_annual_debt_service'])}."
        )
    if cashflow:
        lines.append(
            f"Cash flow {cashflow['period_start']} to {cashflow['period_end']}: average monthly "
            f"inflow {_eur(cashflow['avg_monthly_inflow'])}; {cashflow['months_negative_net']} "
            "months with negative net cash flow; "
            f"{cashflow['negative_balance_days']} days with a negative balance; largest customer "
            f"{cashflow['top_customer']} with "
            f"{(cashflow['top_customer_share'] or 0):.0%} of customer inflow."
        )
        taxes = ", ".join(
            f"{q['quarter']} {_eur(q['amount'])}" for q in cashflow["tax_per_quarter"]
        )
        lines.append(f"Tax payments per quarter: {taxes}.")
    lines.append("Red flags: " + ("; ".join(f"{f['title']}: {f['detail']}" for f in flags)
                                  if flags else "none."))  # fmt: skip
    return "\n".join(lines)


def compute(db: Session, case: Case, errors: list[str] | None = None,
            precedent_requests: list[dict] | None = None) -> Analysis:  # fmt: skip
    """Recompute the analysis from stored figures and transactions (no LLM calls).
    Precedent document requests are kept from the previous run unless new ones are given."""
    company = db.get_one(Company, case.company_id)
    financials = list(db.scalars(select(Financial).where(Financial.case_id == case.id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.case_id == case.id)))
    report_years = [d.year for d in db.scalars(select(Document).where(
        Document.case_id == case.id, Document.kind == "annual_report",
        Document.status == "indexed", Document.year.is_not(None)))]  # fmt: skip
    cashflow = compute_cashflow(transactions)
    existing = cashflow["existing_annual_debt_service"] if cashflow else None
    ratios = compute_ratios(financials, float(case.loan_amount), case.loan_term_months, existing)
    ratios["errors"] = errors or []
    flags = red_flags(ratios, cashflow, company, case.applied_on, report_years)
    analysis = db.get(Analysis, case.id) or Analysis(case_id=case.id)
    if precedent_requests is None:
        precedent_requests = [m for m in (analysis.missing_documents or []) if "share" in m]
    analysis.ratios, analysis.cashflow, analysis.red_flags = ratios, cashflow or {}, flags
    analysis.similar = analysis.lender_matches = None  # inputs changed: recompute on next view
    analysis.missing_documents = missing_documents(case.applied_on, report_years, cashflow,
                                                   precedent_requests)  # fmt: skip
    analysis.computed_at = datetime.now(UTC)
    db.add(analysis)
    text = analysis_text(company.name or "the company", ratios, cashflow, flags)
    header = context_header(company.name, "Financial analysis", "Ratios and cash flow")
    db.execute(delete(Chunk).where(Chunk.case_id == case.id, Chunk.kind == "analysis"))
    db.add(Chunk(case_id=case.id, kind="analysis", section="Financial analysis", text=text,
                 context_header=header, embedding=embed([f"{header}\n{text}"])[0],
                 embedding_model=model_name()))  # fmt: skip
    db.flush()
    return analysis


def run_analysis(db: Session, case_id: uuid.UUID) -> Analysis:
    """Categorise transactions, extract reports not extracted yet, then compute everything."""
    case = db.get_one(Case, case_id)
    for t in db.scalars(select(Transaction).where(Transaction.case_id == case_id)):
        t.category = categorise(t.amount, t.counterparty_name, t.description)
    errors = []
    for doc in unextracted_reports(db, case_id):
        try:
            extract_report(db, doc)
        except LlmError as exc:
            errors.append(f"{doc.filename}: {exc}")
    compute(db, case, errors)
    # Documents lenders often asked for in similar cases join the missing-documents checklist.
    requests = precedent_document_requests(db, find_similar(db, case))
    analysis = compute(db, case, errors, requests)
    db.commit()
    return analysis
