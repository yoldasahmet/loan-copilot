"""Write docs/eval-results.md from the eval results (numbers only, no case data)."""

from eval.common import Result

NOT_RUN = ["Not run: no working LLM was available when the eval ran.", ""]


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def num(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def ms(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f} ms"


def summary_section(ret: Result, ans: Result) -> list[str]:
    lines = [
        "| Pipeline | Recall@5 | MRR@10 | Faithfulness | p95 latency |",
        "|---|---|---|---|---|",
    ]
    for row in ret["configs"]:
        faith = num(ans.get("faithfulness")) if row["rerank"] else "—"
        lines.append(f"| {row['pipeline']} | {pct(row['recall_at_5'])} | "
                     f"{num(row['mrr_at_10'])} | {faith} | {ms(row['p95_ms'])} |")  # fmt: skip
    return [*lines, ""]


def answers_section(ans: Result) -> list[str]:
    if "skipped" in ans:
        return NOT_RUN
    return [
        "| Metric | Value |",
        "|---|---|",
        f"| Faithfulness | {num(ans['faithfulness'])} |",
        f"| Answer relevancy | {num(ans['answer_relevancy'])} |",
        f'| Correct "can\'t find" on {ans["unanswerable"]} unanswerable questions | '
        f"{pct(ans['cant_find_correct'])} |",
        f'| "Can\'t find" on answerable questions | {pct(ans["cant_find_on_answerable"])} |',
        f"| p95 answer latency (retrieval + generation) | {ms(ans['p95_ms'])} |",
        "",
    ]


def extraction_section(ext: Result) -> list[str]:
    if "skipped" in ext:
        return NOT_RUN
    return [
        "| Metric | Value |",
        "|---|---|",
        f"| Reports | {ext['reports']} ({ext['failed']} failed to parse) |",
        f"| Field accuracy (within 0.5%) | {pct(ext['field_accuracy'])} |",
        *[f"| … {layout} layout | {pct(value)} |" for layout, value in ext["by_layout"].items()],
        f"| Reports with validation warnings | {pct(ext['with_warnings'])} |",
        "",
    ]


def backtest_section(bt: Result) -> list[str]:
    if not bt["cases"]:
        return ["Not run: no historical cases imported.", ""]
    hit, agree, cover = bt["lender_hit_at_3"], bt["precedent_agreement"], bt["amount_coverage"]
    return [
        f"{bt['cases']} historical cases that applied from {bt['holdout_from']} are held out; "
        "each sees only cases decided before its own application date.",
        "",
        "| Metric | Cases | App | Random order | Most popular first | Majority outcome |",
        "|---|---|---|---|---|---|",
        f"| Lender hit@3 | {hit['cases']} | {pct(hit['app'])} | {pct(hit['random'])} | "
        f"{pct(hit['most_popular'])} | — |",
        f"| Precedent agreement | {agree['cases']} | {pct(agree['app'])} | — | — | "
        f"{pct(agree['majority_class'])} |",
        f"| Amount coverage (P25–P75) | {cover['cases']} | {pct(cover['app'])} | — | — | — |",
        "",
    ]


def memo_section(memo: Result) -> list[str]:
    if not memo["memos"]:
        return ["Not run: no memos drafted yet (run “Prepare application” on the demo cases).", ""]
    return [
        "| Metric | Value |",
        "|---|---|",
        f"| Memo versions | {memo['memos']} |",
        f"| Every number verified on the first draft | {pct(memo['first_draft'])} |",
        f"| Every number verified after redrafting | {pct(memo['after_redraft'])} |",
        f"| Numbers checked (final drafts) | {memo['numbers_checked']} |",
        f"| Redrafts | {memo['redrafts']} |",
        "",
    ]


HOW_TO_READ = (
    "Recall@5 is the share of answerable questions whose expected page appears in the top 5 "
    "retrieved chunks; MRR@10 rewards finding it early. Latency in the first table is retrieval "
    "only, on CPU. Faithfulness (the share of an answer's statements that its sources support) "
    "and answer relevancy follow the RAGAS definitions, with the same LLM as judge. The backtest "
    "measures whether history-based rankings are informative, not whether a loan should be "
    "granted: the app shows precedents and checks, and the advisor decides. All data is "
    "synthetic, so the numbers show that the pipeline works end to end; they do not predict "
    "accuracy on real applications."
)


def markdown(r: Result) -> str:
    cfg = r["config"]
    lines = [
        "# Evaluation results",
        "",
        f"Run on {cfg['date']} against the synthetic demo data. Written by `make eval` "
        "(`apps/api/eval/`); do not edit by hand.",
        "",
        *summary_section(r["retrieval"], r["answers"]),
        "## Configuration",
        "",
        f"- LLM: `{cfg['llm']}` (also the judge)",
        f"- Embeddings: `{cfg['embedding_model']}`; reranker: `{cfg['reranker_model']}`",
        f"- Golden set: {r['retrieval']['configs'][0]['questions']} answerable questions over "
        "4 demo cases, plus unanswerable ones for the answer metrics",
        "",
        "## Answers (hybrid + rerank)",
        "",
        *answers_section(r["answers"]),
        "## Extraction",
        "",
        *extraction_section(r["extraction"]),
        "## Backtest",
        "",
        *backtest_section(r["backtest"]),
        "## Memo verification",
        "",
        *memo_section(r["memo"]),
        "## How to read this",
        "",
        HOW_TO_READ,
        "",
    ]
    return "\n".join(lines)
