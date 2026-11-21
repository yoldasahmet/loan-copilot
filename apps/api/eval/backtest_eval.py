"""Backtest on history: hold out the cases that applied in the last 12 months of the history.
For each, only cases decided before its application date are searchable (search_cards filters
on first_decided_on), so nothing from its own future leaks in.

- Lender hit@3: an approving lender is in the top 3 of the lender ranking (cases with an
  approval only), against a random order and "most popular lender first".
- Precedent agreement: the majority first outcome of the top 5 similar cases equals the case's
  actual first decision, against "always the most common outcome so far".
- Amount coverage: the granted amount lies within the 25th–75th percentile of the amounts
  approved in the top 5 similar cases (cases with at least 2 such amounts).
"""

import statistics
import uuid
from collections import Counter
from datetime import timedelta
from math import comb

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eval.common import Result, share
from loancopilot.lenders import match_lenders
from loancopilot.models import Case, Decision, Lender
from loancopilot.similar import TOP_K, find_similar

HOLDOUT_DAYS = 365


def first_outcomes(decisions: list[Decision]) -> dict[uuid.UUID, str]:
    """Each case's first decision (by date)."""
    out: dict[uuid.UUID, str] = {}
    for d in sorted(decisions, key=lambda d: d.decided_on):
        out.setdefault(d.case_id, d.decision)
    return out


def majority(outcomes: list[str]) -> str | None:
    """The most common outcome; None on a tie for first place."""
    ranked = Counter(outcomes).most_common(2)
    if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def random_hit_at_3(lenders: int, approving: int) -> float:
    """Chance that a random order puts at least one approving lender in the top 3."""
    return 1 - comb(lenders - approving, 3) / comb(lenders, 3)


def run(db: Session) -> Result:
    decisions = list(db.scalars(select(Decision)))
    lender_ids = list(db.scalars(select(Lender.id).where(Lender.active.is_(True))))
    first = first_outcomes(decisions)
    latest = db.scalar(select(func.max(Case.applied_on)).where(Case.is_historical.is_(True)))
    if latest is None:
        return {"cases": 0}
    held_out = list(db.scalars(select(Case).where(
        Case.is_historical.is_(True), Case.applied_on > latest - timedelta(days=HOLDOUT_DAYS))
        .order_by(Case.applied_on)))  # fmt: skip
    lender_hits, random_hits, popular_hits = [], [], []
    agreement, majority_baseline, coverage = [], [], []
    for case in held_out:
        own = [d for d in decisions if d.case_id == case.id]
        approving = {d.lender_id for d in own if d.decision == "approved"} & set(lender_ids)
        earlier = [d for d in decisions if d.decided_on < case.applied_on]

        if approving:
            ranking = [
                uuid.UUID(item["lender_id"])
                for item in match_lenders(db, case, with_summaries=False)["lenders"]
            ]
            lender_hits.append(bool(approving & set(ranking[:3])))
            random_hits.append(random_hit_at_3(len(lender_ids), len(approving)))
            approvals = Counter(d.lender_id for d in earlier if d.decision == "approved")
            popular = sorted(lender_ids, key=lambda lid: (-approvals[lid], str(lid)))
            popular_hits.append(bool(approving & set(popular[:3])))

        similar = find_similar(db, case, k=TOP_K)
        similar_ids = set(similar)
        actual = first.get(case.id)
        if actual:
            agreement.append(majority([first[c] for c in similar if c in first]) == actual)
            so_far = majority(list(first_outcomes(earlier).values()))
            majority_baseline.append(so_far == actual)

        granted = next((d.amount_granted for d in sorted(own, key=lambda d: d.decided_on)
                        if d.decision == "approved" and d.amount_granted), None)  # fmt: skip
        amounts = [float(d.amount_granted) for d in decisions if d.case_id in similar_ids
                   and d.decision == "approved" and d.amount_granted]  # fmt: skip
        if granted is not None and len(amounts) >= 2:
            q1, _, q3 = statistics.quantiles(amounts, n=4, method="inclusive")
            coverage.append(q1 <= float(granted) <= q3)

    return {
        "cases": len(held_out), "holdout_from": (latest - timedelta(days=HOLDOUT_DAYS)).isoformat(),
        "lender_hit_at_3": {"cases": len(lender_hits),
                            "app": share(sum(lender_hits), len(lender_hits)),
                            "random": share(sum(random_hits), len(random_hits)),
                            "most_popular": share(sum(popular_hits), len(popular_hits))},
        "precedent_agreement": {"cases": len(agreement),
                                "app": share(sum(agreement), len(agreement)),
                                "majority_class": share(sum(majority_baseline),
                                                        len(majority_baseline))},
        "amount_coverage": {"cases": len(coverage), "app": share(sum(coverage), len(coverage))},
    }  # fmt: skip
