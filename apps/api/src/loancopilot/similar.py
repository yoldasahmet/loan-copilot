"""Similar historical cases for an open case: hybrid search + rerank over case cards,
similarity reasons computed in code, lender decisions attached for display only."""

import uuid
from collections import Counter
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from loancopilot.history import profile_text
from loancopilot.models import Analysis, Case, Company, Decision, Financial, Lender
from loancopilot.retrieval import search_cards

TOP_K = 5
PRECEDENT_POOL = 20  # lender matching counts decisions over the top 20
DOCUMENT_REQUEST_SHARE = 0.30


def case_profile(db: Session, case: Case) -> str:
    company = db.get_one(Company, case.company_id)
    financials = list(db.scalars(select(Financial).where(Financial.case_id == case.id)))
    analysis = db.get(Analysis, case.id)
    age = case.applied_on.year - company.founded_year if company.founded_year else None
    return profile_text(sector=company.sector_group, legal_form=company.legal_form, age=age,
                        financials=financials, cashflow=analysis.cashflow if analysis else None,
                        amount=case.loan_amount, purpose=case.loan_purpose,
                        term_months=case.loan_term_months)  # fmt: skip


def _latest(db: Session, case_id: uuid.UUID) -> Financial | None:
    rows = db.scalars(select(Financial).where(Financial.case_id == case_id)
                      .order_by(Financial.year.desc()).limit(1))  # fmt: skip
    return rows.first()


def _solvency(fy: Financial | None) -> float | None:
    if fy is None or fy.equity is None or not fy.total_assets:
        return None
    return float(fy.equity) / float(fy.total_assets)


def reasons(case: Case, company: Company, fy: Financial | None, other: Case,
            other_company: Company, other_fy: Financial | None) -> list[str]:  # fmt: skip
    """Why two cases are alike, computed in code (shown as chips)."""
    out = []
    if company.sector_group and company.sector_group == other_company.sector_group:
        out.append("Same sector")
    revenue, other_revenue = (fy.revenue if fy else None), (other_fy.revenue if other_fy else None)
    if revenue and other_revenue and abs(float(other_revenue) / float(revenue) - 1) <= 0.30:
        out.append("Revenue within ±30%")
    s1, s2 = _solvency(fy), _solvency(other_fy)
    if s1 is not None and s2 is not None and abs(s1 - s2) <= 0.10:
        out.append(f"Solvency {abs(s1 - s2) * 100:.0f} pp apart")
    if case.loan_purpose == other.loan_purpose:
        out.append("Same loan purpose")
    if company.founded_year and other_company.founded_year:
        age = case.applied_on.year - company.founded_year
        other_age = other.applied_on.year - other_company.founded_year
        if abs(age - other_age) <= max(3, age * 0.3):
            out.append("Similar company age")
    if company.legal_form == other_company.legal_form:
        out.append("Same legal form")
    return out


def find_similar(db: Session, case: Case, k: int = TOP_K,
                 rerank: bool | None = None) -> list[uuid.UUID]:  # fmt: skip
    return search_cards(db, case_profile(db, case), before=case.applied_on, k=k, rerank=rerank)


def similar_cases(db: Session, case: Case, k: int = TOP_K) -> list[dict]:
    company = db.get_one(Company, case.company_id)
    fy = _latest(db, case.id)
    lender_names = dict(db.execute(select(Lender.id, Lender.name)).all())
    out = []
    for case_id in find_similar(db, case, k):
        other = db.get_one(Case, case_id)
        other_company = db.get_one(Company, other.company_id)
        other_fy = _latest(db, other.id)
        decisions = db.scalars(select(Decision).where(Decision.case_id == other.id)
                               .order_by(Decision.decided_on))  # fmt: skip
        out.append({
            "case_id": str(other.id), "ref": other.historical_ref,
            "sector_group": other_company.sector_group, "legal_form": other_company.legal_form,
            "region": other_company.city, "revenue": _num(other_fy.revenue if other_fy else None),
            "solvency": _solvency(other_fy), "loan_amount": _num(other.loan_amount),
            "loan_purpose": other.loan_purpose, "term_months": other.loan_term_months,
            "applied_on": other.applied_on.isoformat(),
            "reasons": reasons(case, company, fy, other, other_company, other_fy),
            "decisions": [_decision(d, lender_names) for d in decisions],
        })  # fmt: skip
    return out


def _decision(d: Decision, lender_names: dict) -> dict:
    return {
        "lender": lender_names.get(d.lender_id),
        "decision": d.decision,
        "amount_granted": _num(d.amount_granted),
        "interest_rate": _num(d.interest_rate),
        "term_months": d.term_months,
        "decline_reason": d.decline_reason,
        "documents_requested": d.documents_requested,
        "decided_on": d.decided_on.isoformat(),
    }


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def precedent_document_requests(db: Session, similar_ids: list[uuid.UUID]) -> list[dict]:
    """Documents requested in at least 30% of the similar cases' decisions."""
    decisions = list(db.scalars(select(Decision).where(Decision.case_id.in_(similar_ids))))
    if not decisions:
        return []
    counts = Counter(doc for d in decisions for doc in set(d.documents_requested))
    requests = []
    for doc, n in counts.most_common():
        share = n / len(decisions)
        if share >= DOCUMENT_REQUEST_SHARE:
            requests.append({"document": doc, "share": round(share, 2)})
    return requests
