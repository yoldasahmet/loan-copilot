"""make eval EVAL_DIR=local/eval — runs every eval part against the local database and writes
docs/eval-results.md (numbers only) and the raw results to eval/results/ (gitignored)."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval import answers_eval, backtest_eval, extraction_eval, memo_eval, retrieval_eval
from eval.common import Result, eval_dir, read_jsonl
from eval.report import markdown
from loancopilot import llm
from loancopilot.config import get_settings
from loancopilot.db import SessionLocal

API = Path(__file__).resolve().parents[1]
RESULTS = API / "eval" / "results"
OUTPUT = API.parents[1] / "docs" / "eval-results.md"


def step(name: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {name}", flush=True)


def llm_problem() -> str | None:
    """One tiny call first: without a working LLM the AI parts are skipped, not half-run."""
    try:
        llm.complete(kind="eval_judge", prompt=llm.load_prompt("eval_relevancy"),
                     user_content="Answer: The DSCR is 1.4x.", max_tokens=500)  # fmt: skip
    except llm.LlmError as exc:
        return str(exc)
    return None


def ai_part(problem: str | None, fn: Callable[..., Result], *args: Any) -> Result:
    """Run a part that needs the LLM; if the LLM is or becomes unavailable, mark it not run."""
    if problem:
        return {"skipped": f"No working LLM: {problem}"}
    try:
        return fn(*args)
    except llm.LlmError as exc:
        return {"skipped": f"LLM failed during the run: {exc}"}


def main() -> None:
    folder = eval_dir()
    golden = read_jsonl(folder / "golden_retrieval.jsonl")
    s = get_settings()
    results: dict = {"config": {
        "date": datetime.now(UTC).date().isoformat(), "llm": f"{llm.provider()}:{s.llm_model}",
        "embedding_model": s.embedding_model, "reranker_model": s.reranker_model,
    }}  # fmt: skip
    problem = llm_problem()
    with SessionLocal() as db:
        step("Retrieval")
        results["retrieval"] = retrieval_eval.run(db, golden)
        step("Answers")
        results["answers"] = ai_part(problem, answers_eval.run, db, golden)
        problem = problem or results["answers"].get("skipped")  # don't parse 20 PDFs for nothing
        step("Extraction")
        results["extraction"] = ai_part(problem, extraction_eval.run, db, folder / "extraction")
        step("Backtest")
        results["backtest"] = backtest_eval.run(db)
        step("Memo verification")
        results["memo"] = memo_eval.run(db)
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    (RESULTS / f"{stamp}.json").write_text(json.dumps(results, indent=2, default=str))
    OUTPUT.write_text(markdown(results))
    step(f"Wrote {OUTPUT.relative_to(API.parents[1])}")


if __name__ == "__main__":
    main()
