"""Lender matching: hard checks and precedent counts in code, criteria passages from
retrieval, one LLM call for cited fit summaries. No single score: the facts are shown."""

import statistics
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from loancopilot import llm
from loancopilot.models import Case, Company, Decision, Financial, Lender
from loancopilot.retrieval import Scope, format_sources, search, source_refs
from loancopilot.security import case_pseudonymiser
from loancopilot.similar import PRECEDENT_POOL, case_profile, find_similar

FORM_NAMES = {"bv": "BV", "eenmanszaak": "Eenmanszaak", "vof": "VOF", "other": "Other"}
MIN_DECIDED_FOR_RATIO = 3

SUMMARY_SCHEMA = llm.strict_schema({
    "type": "object",
    "properties": {"summaries": {"type": "array", "items": {
        "type": "object", "properties": {"lender": {"type": "string"},
                                         "summary": {"type": "string"}}}}},
})  # fmt: skip


def _eur(value: Decimal | float) -> str:
    return f"€{float(value):,.0f}"


def hard_checks(lender: Lender, *, amount: Decimal, revenue: Decimal | None,
                years_trading: int | None, sector: str | None,
                legal_form: str) -> list[dict]:  # fmt: skip
    """Each check: label, passed (True/False/None when unknown), the case value and the rule."""

    def check(label: str, passed: bool | None, value: str, rule: str) -> dict:
        return {"check": label, "passed": passed, "value": value, "requirement": rule}

    rule_amount = f"{_eur(lender.min_amount)} – {_eur(lender.max_amount)}"
    excluded = ", ".join(s.replace("_", " ") for s in lender.excluded_sector_groups) or "none"
    forms = ", ".join(FORM_NAMES.get(f, f) for f in lender.allowed_legal_forms)
    return [
        check("Loan amount", lender.min_amount <= amount <= lender.max_amount, _eur(amount),
              rule_amount),
        check("Minimum revenue", None if revenue is None else revenue >= lender.min_revenue,
              "unknown" if revenue is None else _eur(revenue), f"≥ {_eur(lender.min_revenue)}"),
        check("Years trading", None if years_trading is None
              else years_trading >= lender.min_years_trading,
              "unknown" if years_trading is None else f"{years_trading} years",
              f"≥ {lender.min_years_trading} years"),
        check("Sector", None if sector is None else sector not in lender.excluded_sector_groups,
              (sector or "unknown").replace("_", " "), f"excluded: {excluded}"),
        check("Legal form", legal_form in lender.allowed_legal_forms,
              FORM_NAMES.get(legal_form, legal_form), f"allowed: {forms}"),
    ]  # fmt: skip


def precedents(decisions: list[Decision], requested: dict[uuid.UUID, Decimal]) -> dict:
    """'Approved X of Y similar cases' for one lender; withdrawn applications are not decided."""
    approved = [d for d in decisions if d.decision == "approved"]
    declined = [d for d in decisions if d.decision == "declined"]
    ratios = [float(d.amount_granted) / float(requested[d.case_id])
              for d in approved if d.amount_granted is not None]  # fmt: skip
    return {
        "approved": len(approved),
        "declined": len(declined),
        "decided": len(approved) + len(declined),
        "median_granted_ratio": round(statistics.median(ratios), 2) if ratios else None,
    }


def rank_key(item: dict) -> tuple:
    """Failed hard checks last; then approval ratio when Y ≥ 3; then number of decisions."""
    p = item["precedents"]
    has_ratio = p["decided"] >= MIN_DECIDED_FOR_RATIO
    ratio = p["approved"] / p["decided"] if has_ratio else 0.0
    return (not item["passes_hard_checks"], not has_ratio, -ratio, -p["decided"])


def match_lenders(db: Session, case: Case, with_summaries: bool = True) -> dict:
    company = db.get_one(Company, case.company_id)
    latest = db.scalars(select(Financial).where(Financial.case_id == case.id)
                        .order_by(Financial.year.desc()).limit(1)).first()  # fmt: skip
    years = case.applied_on.year - company.founded_year if company.founded_year else None
    similar_ids = find_similar(db, case, k=PRECEDENT_POOL)
    decisions = list(db.scalars(select(Decision).where(Decision.case_id.in_(similar_ids))))
    requested = dict(db.execute(select(Case.id, Case.loan_amount)
                                .where(Case.id.in_(similar_ids))).all())  # fmt: skip
    profile = case_profile(db, case)
    items, hits = [], []
    for lender in db.scalars(select(Lender).where(Lender.active.is_(True)).order_by(Lender.name)):
        checks = hard_checks(
            lender,
            amount=case.loan_amount,
            revenue=latest.revenue if latest else None,
            years_trading=years,
            sector=company.sector_group,
            legal_form=company.legal_form,
        )
        passages = search(db, profile, Scope("lender", lender_ids=(lender.id,)), k=2)
        first = len(hits) + 1
        hits += passages
        items.append({
            "lender_id": str(lender.id), "name": lender.name, "product_type": lender.product_type,
            "typical_rate_min": float(lender.typical_rate_min),
            "typical_rate_max": float(lender.typical_rate_max),
            "checks": checks,
            "passes_hard_checks": all(c["passed"] is not False for c in checks),
            "precedents": precedents([d for d in decisions if d.lender_id == lender.id],
                                     requested),  # fmt: skip
            "source_ids": [f"S{i}" for i in range(first, first + len(passages))],
            "summary": None,
        })  # fmt: skip
    items.sort(key=rank_key)
    errors: list[str] = []
    if with_summaries and items:
        try:
            _add_summaries(db, case, profile, items, hits)
        except llm.LlmError as exc:
            errors.append(str(exc))
    return {"lenders": items, "sources": source_refs(hits), "similar_count": len(similar_ids),
            "errors": errors}  # fmt: skip


def _add_summaries(db: Session, case: Case, profile: str, items: list[dict], hits: list) -> None:
    facts = []
    for item in items:
        p = item["precedents"]
        failed = [c["check"] for c in item["checks"] if c["passed"] is False]
        facts.append(
            f"- {item['name']} ({item['product_type'].replace('_', ' ')}): hard checks "
            f"{'all passed' if not failed else 'failed: ' + ', '.join(failed)}; approved "
            f"{p['approved']} of {p['decided']} similar cases; criteria passages "
            f"{', '.join(item['source_ids']) or 'none'}."
        )
    content = (f"Case profile:\n{profile}\n\nLenders:\n" + "\n".join(facts)
               + f"\n\nCriteria passages:\n{format_sources(hits)}")  # fmt: skip
    result = llm.complete(
        kind="lender_reasons", prompt=llm.load_prompt("lender_reasons"), user_content=content,
        case_id=case.id, source_ids=[str(h.chunk_id) for h in hits], schema=SUMMARY_SCHEMA,
        pii=case_pseudonymiser(db, case.id), max_tokens=6000,
    )  # fmt: skip
    by_name = {s["lender"].lower(): s["summary"] for s in result.data["summaries"]}
    for item in items:
        item["summary"] = by_name.get(item["name"].lower())
