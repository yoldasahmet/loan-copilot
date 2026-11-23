# Evaluation results

Run on 2026-11-23 against the synthetic demo data. Written by `make eval` (`apps/api/eval/`); do not edit by hand.

| Pipeline | Recall@5 | MRR@10 | Faithfulness | p95 latency |
|---|---|---|---|---|
| Dense only | 97.9% | 0.688 | — | 136 ms |
| Keyword only | 87.5% | 0.567 | — | 7 ms |
| Hybrid (RRF) | 97.9% | 0.743 | — | 137 ms |
| Hybrid + rerank | 91.7% | 0.743 | 1.000 | 11,049 ms |

## Configuration

- LLM: `openrouter:z-ai/glm-5.3-flash` (also the judge)
- Embeddings: `BAAI/bge-m3`; reranker: `BAAI/bge-reranker-v2-m3`
- Golden set: 48 answerable questions over 4 demo cases, plus unanswerable ones for the answer metrics

## Answers (hybrid + rerank)

| Metric | Value |
|---|---|
| Faithfulness | 1.000 |
| Answer relevancy | 0.636 |
| Correct "can't find" on 5 unanswerable questions | 100.0% |
| "Can't find" on answerable questions | 0.0% |
| p95 answer latency (retrieval + generation) | 10,239 ms |

## Extraction

| Metric | Value |
|---|---|
| Reports | 20 (0 failed to parse) |
| Field accuracy (within 0.5%) | 100.0% |
| … classic layout | 100.0% |
| … dutch layout | 100.0% |
| … modern layout | 100.0% |
| Reports with validation warnings | 0.0% |

## Backtest

46 historical cases that applied from 2025-09-28 are held out; each sees only cases decided before its own application date.

| Metric | Cases | App | Random order | Most popular first | Majority outcome |
|---|---|---|---|---|---|
| Lender hit@3 | 29 | 93.1% | 66.0% | 79.3% | — |
| Precedent agreement | 46 | 43.5% | — | — | 58.7% |
| Amount coverage (P25–P75) | 28 | 21.4% | — | — | — |

## Memo verification

| Metric | Value |
|---|---|
| Memo versions | 4 |
| Every number verified on the first draft | 75.0% |
| Every number verified after redrafting | 100.0% |
| Numbers checked (final drafts) | 337 |
| Redrafts | 1 |

## How to read this

Recall@5 is the share of answerable questions whose expected page appears in the top 5 retrieved chunks; MRR@10 rewards finding it early. Latency in the first table is retrieval only, on CPU. Faithfulness (the share of an answer's statements that its sources support) and answer relevancy follow the RAGAS definitions, with the same LLM as judge. The backtest measures whether history-based rankings are informative, not whether a loan should be granted: the app shows precedents and checks, and the advisor decides. All data is synthetic, so the numbers show that the pipeline works end to end; they do not predict accuracy on real applications.
