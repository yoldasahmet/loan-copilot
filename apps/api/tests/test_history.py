import copy
import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from loancopilot.db import SessionLocal
from loancopilot.history import import_jsonl
from loancopilot.models import Case, CaseCard, Decision, Lender
from loancopilot.retrieval import search_cards

LINE = {
    "company": {"legal_form": "bv", "sbi_code": "4322", "founded_year": 2010, "employees": 25,
                "region": "Overijssel"},
    "application": {"applied_on": "2024-03-15", "amount": 400000, "purpose": "equipment",
                    "term_months": 60},
    "financials": [{"year": 2022, "revenue": 2800000, "ebitda": 300000, "equity": 700000,
                    "total_assets": 1800000},
                   {"year": 2023, "revenue": 3100000, "ebitda": 350000, "equity": 760000,
                    "total_assets": 1900000}],
    "cashflow_summary": {"avg_monthly_inflow": 255000, "negative_balance_days": 0,
                         "top_customer_share": 0.2, "existing_annual_debt_service": 90000},
    "decisions": [{"lender_name": "Testbank", "decision": "approved", "amount_granted": 380000,
                   "interest_rate": 0.065, "term_months": 60, "decline_reason": None,
                   "documents_requested": ["A cash-flow forecast"], "decided_on": "2024-04-10"}],
}  # fmt: skip


def line(**changes) -> dict:  # noqa: ANN003
    out = copy.deepcopy(LINE)
    for path, value in changes.items():
        target = out
        *parents, last = path.split("__")
        for p in parents:
            target = target[p]
        target[last] = value
    return out


def make_lender(name: str = "Testbank", **kw) -> Lender:  # noqa: ANN003
    values = {
        "product_type": "term_loan", "min_amount": 100_000, "max_amount": 2_000_000,
        "min_revenue": 1_000_000, "min_years_trading": 3,
        "excluded_sector_groups": ["hospitality"], "allowed_legal_forms": ["bv", "vof"],
        "typical_rate_min": Decimal("0.055"), "typical_rate_max": Decimal("0.085"),
        "active": True,
    } | kw  # fmt: skip
    with SessionLocal() as db:
        lender = Lender(name=name, **values)
        db.add(lender)
        db.commit()
        return lender


def jsonl(*rows) -> str:  # noqa: ANN002
    return "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows)


def test_import_valid_and_broken_lines() -> None:
    make_lender()
    named = line()
    named["company"]["name"] = "Real Company B.V."  # no name fields allowed
    text = jsonl(line(), named, line(application__purpose="yacht"),
                 line(decisions=[{**LINE["decisions"][0], "lender_name": "Ghost Bank"}]),
                 "{not json", line(application__applied_on="2024-06-01"))  # fmt: skip
    with SessionLocal() as db:
        result = import_jsonl(db, text)
    assert result["imported"] == 2
    errors = {e["line"]: e["message"] for e in result["errors"]}
    assert set(errors) == {2, 3, 4, 5}
    assert "company.name" in errors[2] and "Extra inputs" in errors[2]
    assert "application.purpose" in errors[3]
    assert "Ghost Bank" in errors[4]
    with SessionLocal() as db:
        refs = sorted(db.scalars(select(Case.historical_ref).where(Case.is_historical.is_(True))))
        assert refs == ["H-0001", "H-0002"]
        card = db.scalars(select(CaseCard)).first()
        assert card.embedding is not None and card.first_decided_on == date(2024, 4, 10)
        assert "Revenue €3.1 million in 2023" in card.profile_text
        assert "revenue growth +11%" in card.profile_text
        for outcome in ("approved", "declined", "Testbank", "380"):  # outcomes never embedded
            assert outcome not in card.profile_text
        assert db.scalar(select(Decision.decision)) == "approved"
    with SessionLocal() as db:  # a second import continues the numbering
        assert import_jsonl(db, jsonl(line()))["imported"] == 1
        assert "H-0003" in db.scalars(select(Case.historical_ref)).all()


def test_similar_search_never_sees_cases_decided_later() -> None:
    make_lender()
    early = line()
    late = line(application__applied_on="2026-09-01",
                decisions=[{**LINE["decisions"][0], "decided_on": "2026-10-01"}])  # fmt: skip
    with SessionLocal() as db:
        import_jsonl(db, jsonl(early, late))
        query = db.scalars(select(CaseCard.profile_text)).first()
        found = search_cards(db, query, before=date(2026, 9, 15), k=10)
        assert len(found) == 1  # only the case decided in 2024
        assert len(search_cards(db, query, before=date(2026, 12, 1), k=10)) == 2
        assert search_cards(db, query, before=date(2024, 4, 10), k=10) == []  # strictly before
