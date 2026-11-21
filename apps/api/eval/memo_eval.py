"""Memo verification, read from the memos the agent drafted for the open cases: the share of
memo versions with every number verified on the first draft, and after redrafting."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eval.common import Result, share
from loancopilot.models import Case, Memo


def run(db: Session) -> Result:
    memos = list(db.scalars(select(Memo).join(Case, Case.id == Memo.case_id)
                            .where(Case.is_historical.is_(False))))  # fmt: skip
    attempts = [m.verification.get("attempts", []) for m in memos]
    attempts = [a for a in attempts if a]
    return {
        "memos": len(attempts),
        "first_draft": share(sum(not a[0]["unverified"] for a in attempts), len(attempts)),
        "after_redraft": share(sum(not a[-1]["unverified"] for a in attempts), len(attempts)),
        "numbers_checked": sum(a[-1]["total"] for a in attempts),
        "redrafts": sum(len(a) - 1 for a in attempts),
    }
