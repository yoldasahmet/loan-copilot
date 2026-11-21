import uuid
from decimal import Decimal
from types import SimpleNamespace

from loancopilot.lenders import hard_checks, precedents, rank_key
from loancopilot.models import Lender

LENDER = Lender(name="Testbank", product_type="term_loan", min_amount=Decimal(100_000),
                max_amount=Decimal(2_000_000), min_revenue=Decimal(1_000_000), min_years_trading=3,
                excluded_sector_groups=["hospitality"], allowed_legal_forms=["bv", "vof"],
                typical_rate_min=Decimal("0.055"), typical_rate_max=Decimal("0.085"))  # fmt: skip


def checks(**kw) -> dict[str, bool | None]:  # noqa: ANN003
    args = dict(amount=Decimal(450_000), revenue=Decimal(3_400_000), years_trading=12,
                sector="construction", legal_form="bv") | kw  # fmt: skip
    return {c["check"]: c["passed"] for c in hard_checks(LENDER, **args)}


def test_all_checks_pass() -> None:
    assert set(checks().values()) == {True}


def test_each_hard_check_can_fail() -> None:
    assert checks(amount=Decimal(99_999))["Loan amount"] is False
    assert checks(amount=Decimal(2_000_001))["Loan amount"] is False
    assert checks(amount=Decimal(100_000))["Loan amount"] is True  # inclusive bounds
    assert checks(revenue=Decimal(999_999))["Minimum revenue"] is False
    assert checks(years_trading=2)["Years trading"] is False
    assert checks(years_trading=3)["Years trading"] is True
    assert checks(sector="hospitality")["Sector"] is False
    assert checks(legal_form="eenmanszaak")["Legal form"] is False


def test_unknown_values_are_not_failures() -> None:
    result = checks(revenue=None, years_trading=None, sector=None)
    assert result["Minimum revenue"] is None and result["Years trading"] is None
    assert result["Sector"] is None


def test_check_rows_show_value_and_rule() -> None:
    row = hard_checks(LENDER, amount=Decimal(450_000), revenue=None, years_trading=12,
                      sector="construction", legal_form="vof")[0]  # fmt: skip
    assert row == {"check": "Loan amount", "passed": True, "value": "€450,000",
                   "requirement": "€100,000 – €2,000,000"}  # fmt: skip


def test_precedent_counts_and_median_ratio() -> None:
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    requested = {a: Decimal(100_000), b: Decimal(200_000), c: Decimal(100_000), d: Decimal(50_000)}
    decisions = [
        SimpleNamespace(case_id=a, decision="approved", amount_granted=Decimal(80_000)),
        SimpleNamespace(case_id=b, decision="approved", amount_granted=Decimal(200_000)),
        SimpleNamespace(case_id=c, decision="declined", amount_granted=None),
        SimpleNamespace(case_id=d, decision="withdrawn", amount_granted=None),
    ]
    assert precedents(decisions, requested) == {"approved": 2, "declined": 1, "decided": 3,
                                                "median_granted_ratio": 0.9}  # fmt: skip


def test_ranking_rule() -> None:
    def item(name: str, approved: int, decided: int, passes: bool = True) -> dict:
        return {"name": name, "passes_hard_checks": passes,
                "precedents": {"approved": approved, "decided": decided}}  # fmt: skip

    items = [item("few", 2, 2), item("fails", 9, 9, passes=False), item("good", 6, 8),
             item("best", 3, 3), item("weak", 1, 4), item("none", 0, 0)]  # fmt: skip
    assert [i["name"] for i in sorted(items, key=rank_key)] == [
        "best", "good", "weak", "few", "none", "fails"]  # fmt: skip
