"""Ratios, annuity/DSCR, categories, cash flow and every red-flag threshold."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from loancopilot.analysis import (
    THRESHOLDS,
    annuity_annual,
    categorise,
    compute_cashflow,
    compute_ratios,
    missing_documents,
    red_flags,
    status,
)
from loancopilot.models import Financial


def fin(year: int, **values: float) -> Financial:
    base = dict(revenue=3_400_000, cost_of_sales=1_870_000, gross_profit=1_530_000,
                operating_expenses=1_122_000, ebitda=408_000, depreciation=90_000,
                interest_expense=30_000, net_income=230_000, total_assets=2_000_000,
                current_assets=1_200_000, cash=324_000, equity=760_000,
                current_liabilities=790_000, long_term_debt=450_000)  # fmt: skip
    base.update(values)
    return Financial(year=year, **{k: Decimal(str(v)) for k, v in base.items()})


def ratio(result: dict, key: str) -> dict:
    return next(i for i in result["items"] if i["key"] == key)


def test_annuity_known_value() -> None:
    # €450,000 over 60 months at 8%: monthly payment €9,124.38 (amortises to zero)
    assert annuity_annual(450_000, 0.08, 60) == pytest.approx(9_124.3774 * 12, abs=0.01)
    assert annuity_annual(120_000, 0.0, 48) == pytest.approx(30_000)


def test_every_ratio_and_dscr() -> None:
    result = compute_ratios([fin(2024, revenue=3_036_000), fin(2025)], 450_000, 60, 101_904.0)
    assert ratio(result, "solvency")["value"] == pytest.approx(0.38)
    assert ratio(result, "current_ratio")["value"] == pytest.approx(1_200_000 / 790_000)
    assert ratio(result, "ebitda_margin")["value"] == pytest.approx(0.12)
    assert ratio(result, "revenue_growth")["value"] == pytest.approx(3_400_000 / 3_036_000 - 1)
    assert ratio(result, "debt_ebitda")["value"] == pytest.approx(450_000 / 408_000)
    assert ratio(result, "interest_coverage")["value"] == pytest.approx(408_000 / 30_000)
    new_ds = annuity_annual(450_000, 0.08, 60)
    assert ratio(result, "dscr")["value"] == pytest.approx(408_000 / (101_904 + new_ds))
    assert result["assumptions"]["interest_rate"] == 0.08
    assert result["assumptions"]["new_annual_debt_service"] == pytest.approx(new_ds, abs=0.01)
    assert ratio(result, "solvency")["previous"] == pytest.approx(0.38)  # 2024 uses same defaults
    assert all(i["status"] == "green" for i in result["items"] if i["threshold"] is not None)


def test_ratio_status_bands() -> None:
    assert status(0.19, 0.20, True) == "red"
    assert status(0.21, 0.20, True) == "amber"
    assert status(0.30, 0.20, True) == "green"
    assert status(4.1, 4.0, False) == "red"
    assert status(3.8, 4.0, False) == "amber"
    assert status(None, 0.2, True) == "neutral"


def test_negative_ebitda_makes_debt_ebitda_red() -> None:
    result = compute_ratios([fin(2025, ebitda=-10_000)], 100_000, 36, 0.0)
    assert ratio(result, "debt_ebitda")["status"] == "red"
    assert ratio(result, "debt_ebitda")["value"] is None


@pytest.mark.parametrize(
    ("counterparty", "description", "amount", "expected"),
    [
        ("Belastingdienst", "Payroll tax March 2026", -1500, "tax"),
        ("Payroll net salaries", "Salaries March 2026", -20000, "salaries"),
        ("Grachtzijde Bank N.V.", "Loan repayment contract 1234-56", -8000, "loan_repayment"),
        ("Kesdra Vastgoed B.V.", "Rent March 2026", -4000, "rent"),
        ("Bank fees", "Account and payment fees", -95, "bank_fees"),
        ("Klant B.V.", "Payment invoice INV-2026-101", 12000, "customers"),
        ("Leverancier B.V.", "Invoice 22331", -3000, "suppliers"),
        (None, "Cash withdrawal", -200, "other"),
    ],
)
def test_categories(counterparty, description, amount, expected) -> None:  # noqa: ANN001
    assert categorise(Decimal(amount), counterparty, description) == expected


def tx(day: str, amount: float, category: str, name: str = "X", balance: float | None = None):  # noqa: ANN201
    balance_after = None if balance is None else Decimal(str(balance))
    return SimpleNamespace(
        booked_on=date.fromisoformat(day),
        amount=Decimal(str(amount)),
        category=category,
        counterparty_name=name,
        balance_after=balance_after,
    )


def test_cashflow_metrics() -> None:
    txs = [
        tx("2025-11-03", 1000, "customers", "A", 1000),
        tx("2025-11-20", -1500, "tax", "Belastingdienst", -500),  # negative from 20 Nov
        tx("2025-12-10", 3000, "customers", "B", 2500),
        tx("2026-01-15", -600, "loan_repayment", "Bank", 1900),
        tx("2026-10-30", 500, "customers", "A", 2400),
    ]
    cf = compute_cashflow(txs)
    assert cf["period_start"] == "2025-11-01" and cf["period_end"] == "2026-10-30"
    nov = cf["months"][0]
    assert (nov["inflow"], nov["outflow"], nov["net"], nov["end_balance"]) == (
        1000.0, 1500.0, -500.0, -500.0)  # fmt: skip
    assert cf["negative_balance_days"] == 20  # 20 Nov .. 9 Dec
    assert cf["months_negative_net"] == 2  # Nov and Jan
    assert cf["avg_monthly_inflow"] == pytest.approx(4500 / 12, abs=0.01)
    assert cf["top_customer"] == "B" and cf["top_customer_share"] == pytest.approx(
        3000 / 4500, 1e-3
    )
    assert cf["existing_annual_debt_service"] == 600.0
    quarters = {q["quarter"]: q["amount"] for q in cf["tax_per_quarter"]}
    assert quarters["2025-Q4"] == 1500.0 and quarters["2026-Q3"] == 0.0


def _flags(**kw) -> set[str]:  # noqa: ANN003
    ratios = kw.get("ratios", {"items": []})
    cashflow = kw.get("cashflow")
    company = SimpleNamespace(founded_year=kw.get("founded", 2010))
    return {f["code"] for f in red_flags(ratios, cashflow, company, date(2026, 11, 1),
                                         kw.get("years", [2024, 2025]))}  # fmt: skip


@pytest.mark.parametrize(
    ("key", "bad", "good"),
    [("solvency", {"equity": 390_000}, {"equity": 410_000}),          # 19.5% vs 20.5%
     ("current_ratio", {"current_assets": 780_000}, {"current_assets": 800_000}),
     ("debt_ebitda", {"long_term_debt": 1_640_000}, {"long_term_debt": 1_620_000}),
     ("interest_coverage", {"interest_expense": 140_000}, {"interest_expense": 130_000})],
)  # fmt: skip
def test_ratio_red_flags_at_thresholds(key: str, bad: dict, good: dict) -> None:
    assert key in _flags(ratios=compute_ratios([fin(2025, **bad)], 100_000, 60, 0.0))
    assert key not in _flags(ratios=compute_ratios([fin(2025, **good)], 100_000, 60, 0.0))


def test_revenue_decline_flag() -> None:
    bad = compute_ratios([fin(2024, revenue=3_000_000), fin(2025, revenue=2_520_000)], 1, 60, 0.0)
    good = compute_ratios([fin(2024, revenue=3_000_000), fin(2025, revenue=2_580_000)], 1, 60, 0.0)
    assert "revenue_growth" in _flags(ratios=bad)  # -16%
    assert "revenue_growth" not in _flags(ratios=good)  # -14%


def test_dscr_flag() -> None:
    # EBITDA 408k; DSCR = 408k / (existing + new). Threshold 1.25.
    new_ds = annuity_annual(450_000, 0.08, 60)
    bad_existing = 408_000 / 1.24 - new_ds
    good_existing = 408_000 / 1.26 - new_ds
    assert "dscr" in _flags(ratios=compute_ratios([fin(2025)], 450_000, 60, bad_existing))
    assert "dscr" not in _flags(ratios=compute_ratios([fin(2025)], 450_000, 60, good_existing))


def cashflow(**kw) -> dict:  # noqa: ANN003
    base = {"negative_balance_days": 0, "top_customer_share": 0.2,
            "tax_per_quarter": [{"quarter": "2026-Q1", "amount": 100.0}]}  # fmt: skip
    return base | kw


def test_cashflow_flags_at_thresholds() -> None:
    limit = THRESHOLDS["negative_balance_days_max"]
    assert "overdraft" in _flags(cashflow=cashflow(negative_balance_days=limit + 1))
    assert "overdraft" not in _flags(cashflow=cashflow(negative_balance_days=limit))
    assert "customer_concentration" in _flags(cashflow=cashflow(top_customer_share=0.41))
    assert "customer_concentration" not in _flags(cashflow=cashflow(top_customer_share=0.40))
    no_tax = cashflow(tax_per_quarter=[{"quarter": "2026-Q3", "amount": 0.0}])
    assert "tax_gap" in _flags(cashflow=no_tax)
    assert "tax_gap" not in _flags(cashflow=cashflow())


def test_company_age_and_report_count_flags() -> None:
    assert "young_company" in _flags(founded=2024)  # 2 years at application in 2026
    assert "young_company" not in _flags(founded=2023)  # 3 years
    assert "few_reports" in _flags(years=[2025])
    assert "few_reports" not in _flags(years=[2024, 2025])


def test_missing_documents_checklist() -> None:
    cf = {"covered_days": 365, "period_end": "2026-10-31"}
    items = missing_documents(date(2026, 11, 18), [2025], cf,
                              [{"document": "A cash-flow forecast", "share": 0.4}])  # fmt: skip
    status_by_doc = {i["document"]: i["present"] for i in items}
    assert status_by_doc == {"Annual report 2025": True, "Annual report 2024": False,
                             "Bank statements for the last 12 months": True,
                             "A cash-flow forecast": False}  # fmt: skip
    assert not missing_documents(date(2026, 11, 18), [], None)[2]["present"]
