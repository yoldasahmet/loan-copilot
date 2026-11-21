import uuid
from decimal import Decimal

from eval.backtest_eval import majority, random_hit_at_3
from eval.common import p95
from eval.extraction_eval import correct
from eval.report import markdown
from eval.retrieval_eval import first_relevant_rank
from loancopilot.retrieval import Hit


def hit(filename: str, page_from: int, page_to: int | None = None) -> Hit:
    return Hit(uuid.uuid4(), uuid.uuid4(), filename, "section", None, page_from, page_to, "", 0.0)


def test_first_relevant_rank_needs_document_and_page() -> None:
    hits = [hit("other.pdf", 2), hit("report.pdf", 4), hit("report.pdf", 1, 3)]
    assert first_relevant_rank(hits, "report.pdf", 2) == 3
    assert first_relevant_rank(hits, "report.pdf", 5) is None


def test_majority_is_none_on_a_tie() -> None:
    assert majority(["declined", "approved", "declined"]) == "declined"
    assert majority(["declined", "approved"]) is None
    assert majority([]) is None


def test_random_hit_at_3() -> None:
    assert random_hit_at_3(6, 1) == 0.5
    assert random_hit_at_3(6, 4) == 1.0


def test_p95() -> None:
    assert p95([]) is None
    assert p95([float(v) for v in range(1, 101)]) == 95.0
    assert p95([7.0]) == 7.0


def test_extraction_tolerance_is_half_a_percent() -> None:
    assert correct(Decimal("1005"), 1000)
    assert not correct(Decimal("1006"), 1000)
    assert not correct(None, 1000)
    assert correct(Decimal("0"), 0)


def test_report_marks_skipped_parts() -> None:
    config = {"pipeline": "Dense only", "rerank": False, "questions": 10, "recall_at_5": 0.5,
              "mrr_at_10": 0.25, "p95_ms": 12.0}  # fmt: skip
    results = {
        "config": {
            "date": "2026-11-21",
            "llm": "x:y",
            "embedding_model": "e",
            "reranker_model": "r",
        },  # fmt: skip
        "retrieval": {"configs": [config]},
        "answers": {"skipped": "No working LLM"},
        "extraction": {"skipped": "No working LLM"},
        "backtest": {
            "cases": 0,
            "lender_hit_at_3": {"cases": 0, "app": None, "random": None, "most_popular": None},
            "precedent_agreement": {"cases": 0, "app": None, "majority_class": None},
            "amount_coverage": {"cases": 0, "app": None},
        },  # fmt: skip
        "memo": {
            "memos": 0,
            "first_draft": None,
            "after_redraft": None,
            "numbers_checked": 0,
            "redrafts": 0,
        },  # fmt: skip
    }
    text = markdown(results)
    assert "| Dense only | 50.0% | 0.250 | — | 12 ms |" in text
    assert text.count("Not run: no working LLM") == 2
