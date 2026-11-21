"""Small helpers shared by the eval parts."""

import json
import math
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from loancopilot.models import Case, Company, User


def eval_dir() -> Path:
    value = os.environ.get("EVAL_DIR")
    if not value:
        raise SystemExit("Set EVAL_DIR, e.g. make eval EVAL_DIR=local/eval")
    return Path(value)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def timed[T](fn: Callable[..., T], *args: Any) -> tuple[T, float]:
    """Run fn(*args) and return (result, milliseconds)."""
    started = time.perf_counter()
    result = fn(*args)
    return result, (time.perf_counter() - started) * 1000


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def share(hits: int, total: int) -> float | None:
    return hits / total if total else None


def open_case(db: Session, company_name: str) -> tuple[Case, User]:
    """An open (non-historical) case by company name, and the advisor it is assigned to."""
    case = db.scalars(
        select(Case).join(Company, Company.id == Case.company_id)
        .where(Company.name == company_name, Case.is_historical.is_(False))
    ).first()  # fmt: skip
    if case is None or case.advisor_id is None:
        raise SystemExit(f"Case for {company_name!r} not found: load the demo data first.")
    return case, db.get_one(User, case.advisor_id)


def admin(db: Session) -> User:
    user = db.scalars(select(User).where(User.role == "admin")).first()
    if user is None:
        raise SystemExit("No admin user: load the demo data first.")
    return user


Result = dict[str, Any]
