"""Retrieval: recall@5 and MRR@10 on the golden questions, for four pipeline configurations."""

from sqlalchemy.orm import Session

from eval.common import Result, open_case, p95, timed
from loancopilot.retrieval import Hit, Scope, search

CONFIGS = [
    ("Dense only", "dense", False),
    ("Keyword only", "keyword", False),
    ("Hybrid (RRF)", "hybrid", False),
    ("Hybrid + rerank", "hybrid", True),
]


def first_relevant_rank(hits: list[Hit], document: str, page: int) -> int | None:
    """1-based rank of the first chunk from the expected document that covers the page."""
    for rank, h in enumerate(hits, start=1):
        last = h.page_to or h.page_from
        if h.filename == document and h.page_from and h.page_from <= page <= last:
            return rank
    return None


def run(db: Session, golden: list[dict]) -> Result:
    questions = [g for g in golden if g["answerable"]]
    rows = []
    for name, mode, rerank in CONFIGS:
        ranks, latencies = [], []
        for g in questions:
            case, user = open_case(db, g["company"])
            scope = Scope("case", user=user, case_id=case.id)
            hits, ms = timed(search, db, g["question"], scope, 10, mode, rerank)
            ranks.append(first_relevant_rank(hits, g["expected_document"], g["expected_page"]))
            latencies.append(ms)
        rows.append({
            "pipeline": name, "mode": mode, "rerank": rerank, "questions": len(questions),
            "recall_at_5": sum(1 for r in ranks if r and r <= 5) / len(questions),
            "mrr_at_10": sum(1 / r for r in ranks if r and r <= 10) / len(questions),
            "p95_ms": p95(latencies),
        })  # fmt: skip
    return {"configs": rows}
