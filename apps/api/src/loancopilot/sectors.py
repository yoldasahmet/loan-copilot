"""Sector groups (from the first two SBI digits) and revenue bands."""

from decimal import Decimal

SECTOR_GROUPS = [
    "construction", "hospitality", "retail", "wholesale", "manufacturing", "transport_logistics",
    "it_services", "professional_services", "healthcare_practices", "agriculture",
]  # fmt: skip

_RANGES: list[tuple[int, int, str]] = [
    (1, 3, "agriculture"),
    (10, 33, "manufacturing"),
    (41, 43, "construction"),
    (45, 45, "retail"),
    (46, 46, "wholesale"),
    (47, 47, "retail"),
    (49, 53, "transport_logistics"),
    (55, 56, "hospitality"),
    (58, 63, "it_services"),
    (69, 75, "professional_services"),
    (86, 88, "healthcare_practices"),
]
SECTOR_BY_SBI2: dict[str, str] = {
    f"{n:02d}": group for lo, hi, group in _RANGES for n in range(lo, hi + 1)
}


def sector_group(sbi_code: str | None) -> str | None:
    return SECTOR_BY_SBI2.get((sbi_code or "")[:2])


def revenue_band(revenue: Decimal | float | None) -> str | None:
    if revenue is None:
        return None
    value = float(revenue)
    if value < 500_000:
        return "<0.5M"
    if value < 2_000_000:
        return "0.5–2M"
    if value < 10_000_000:
        return "2–10M"
    return ">10M"
