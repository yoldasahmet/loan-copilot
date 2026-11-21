import pytest

from loancopilot.memo import Source, extract_numbers, missing_sections, verify_numbers

EVIDENCE = [
    Source("S1", "figure", "Figures 2025",
           "revenue: €3,400,000\nebitda: €408,000\ntotal assets: €1,234,567"),
    Source("S2", "metric", "Ratios", "Solvency: 38.0%\nDSCR: 1.35x\nEBITDA margin: 12.5%"),
    Source("S3", "metric", "Loan request", "Loan request: €450,000 over 60 months."),
]  # fmt: skip


@pytest.mark.parametrize(
    ("text", "value"),
    [("€1.2M", 1_200_000), ("€450k", 450_000), ("1,234,567", 1_234_567), ("12.5%", 12.5),
     ("1.35x", 1.35), ("€3.4 million", 3_400_000), ("€408,000", 408_000)],
)  # fmt: skip
def test_extracts_every_format(text: str, value: float) -> None:
    [n] = extract_numbers(f"The figure is {text} [S1].")
    assert n.value == pytest.approx(value)


def test_years_citations_list_markers_and_small_counts_are_skipped() -> None:
    text = "## 1. Summary\nIn 2025 [S12] the company had 3 lenders and 2 reports.\n1. First"
    assert extract_numbers(text) == []


def test_all_formats_verify_against_the_evidence() -> None:
    memo = ("Revenue reached €3.4M [S1] (€3,400,000), EBITDA €408k [S1], solvency 38% [S2], "
            "DSCR 1.35x [S2], margin 12.5% [S2] and total assets 1,234,567 [S1]. "
            "The request is €450,000 over 60 months [S3].")  # fmt: skip
    result = verify_numbers(memo, EVIDENCE)
    assert result["unverified"] == []
    assert result["total"] == result["verified"] == 9


def test_display_rounding_tolerance() -> None:
    # €1.2M covers 1.15–1.25M (rounding to one decimal); 1,240,000 is in the evidence? no.
    evidence = [Source("S1", "figure", "x", "assets €1,236,000")]
    assert verify_numbers("Assets of €1.2M [S1].", evidence)["unverified"] == []
    assert verify_numbers("Assets of €1.3M [S1].", evidence)["unverified"] == ["€1.3M"]
    assert verify_numbers("Assets of €1,250,000 [S1].", evidence)["unverified"] == ["€1,250,000"]
    assert verify_numbers("Assets of €1,240,000 [S1].", evidence)["unverified"] == []  # ±1%


def test_invented_numbers_are_reported_once() -> None:
    result = verify_numbers("Revenue grew 17% [S1]; 17% again; DSCR 2.10x [S2].", EVIDENCE)
    assert result["unverified"] == ["17%", "2.10x"]
    assert result["verified"] == 0 and result["total"] == 3


def test_missing_sections() -> None:
    assert "Cash flow" in missing_sections("## Summary\nx\n## Company\ny")
    full = "\n".join(f"## {s}\ntext" for s in ["Summary", "Company", "Loan request",
                     "Financial analysis", "Cash flow", "Risks and mitigants", "Similar cases",
                     "Lender options", "Missing documents"])  # fmt: skip
    assert missing_sections(full) == []
