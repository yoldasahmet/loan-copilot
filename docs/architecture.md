# Architecture

SME Loan Copilot is two apps and one database: a Next.js UI, a FastAPI backend and
Postgres with pgvector. Embeddings and reranking run locally; only `llm.py` talks to an
LLM provider, and it pseudonymises names before every call. Decisions behind this design are
in [`adr/`](adr/).

## System

```mermaid
flowchart LR
  advisor([Loan advisor / admin]) --> web

  subgraph browser_side [Browser]
    web["Next.js UI<br/>App Router, shadcn/ui<br/>:3000"]
  end

  web -- "/api/* (rewrite)<br/>session cookie" --> api

  subgraph server [API process]
    api["FastAPI<br/>routes/*"]
    bg["Background tasks<br/>ingestion, prepare agent"]
    models["Local models<br/>bge-m3 embeddings<br/>bge-reranker-v2-m3"]
    llmpy["llm.py<br/>pseudonymise → call → restore<br/>rate limit, ai_runs log"]
    api --> bg
    api --> models
    bg --> models
    api --> llmpy
    bg --> llmpy
  end

  api --> db
  bg --> db
  files[("DATA_DIR/files<br/>uploaded PDFs, statements")]
  api --> files
  bg --> files

  db[("Postgres 17 + pgvector<br/>tables, HNSW vectors,<br/>tsvector full-text,<br/>LangGraph checkpoints")]

  llmpy -- HTTPS --> provider["LLM provider<br/>Anthropic, OpenAI or OpenRouter"]
  api -. "OTel spans (optional)" .-> phoenix["Arize Phoenix<br/>:6006"]
  bg -.-> phoenix
```

| Part | Where | Notes |
|---|---|---|
| UI | `apps/web/src/` | Every screen has empty, loading and error states |
| API | `apps/api/src/loancopilot/routes/` | All under `/api`; access control through `allowed_case_ids` |
| Domain code | `apps/api/src/loancopilot/*.py` | One module per concern; plain functions |
| Database | `models.py`, `alembic/` | One Postgres for rows, vectors, full-text and agent checkpoints |
| Evaluation | `apps/api/eval/` | Code only; data comes from `EVAL_DIR` |

## Ingestion → retrieval → generation

```mermaid
flowchart TB
  upload["Upload<br/>magic-byte + size checks,<br/>sha256 dedup"] --> kind{PDF or statement?}
  kind -- "PDF" --> docling["Docling<br/>per-page markdown, tables kept"]
  kind -- "CAMT.053 / CSV" --> tx["transactions rows<br/>(never chunked)"]
  docling --> chunk["Chunker<br/>sections + whole tables,<br/>200–700 tokens, page ranges"]
  chunk --> scan["Injection scan<br/>flagged documents stay out<br/>of LLM context until allowed"]
  scan --> embed["Context header + bge-m3"]
  embed --> store[("chunks<br/>vector + tsvector")]

  chunk --> extract["LLM extracts figures<br/>from table chunks"]
  extract --> validate["Code validates<br/>page lookup, accounting identities"]
  validate --> analysis["Ratios, cash flow, red flags<br/>(Python)"]
  tx --> analysis
  analysis --> achunk["analysis chunk<br/>(text from code)"] --> store

  question(["Chat question"]) --> rewrite["Query rewrite<br/>(follow-ups only)"]
  rewrite --> dense["Dense top 40<br/>pgvector"]
  rewrite --> kw["Keyword top 40<br/>websearch_to_tsquery"]
  store --> dense
  store --> kw
  dense --> rrf["RRF k=60"]
  kw --> rrf
  rrf --> rerank["Cross-encoder<br/>top 30 → top 6"]
  rerank --> gen["LLM answer<br/>[S1]…[Sn] citations,<br/>or the can't-find reply"]
  gen --> sse(["SSE stream + source panel"])
```

The access filter is part of the retrieval SQL (`Chunk.case_id IN allowed_case_ids(user)`),
so another advisor's chunks are never even candidates.

## "Prepare application" agent

A LangGraph graph with the Postgres checkpointer; thread id `{case_id}:{run_number}`. Each
node updates `prepare_runs.steps`, which the UI polls.

```mermaid
flowchart TB
  start([Start]) --> check["check_documents<br/>missing documents noted"]
  check --> analyse["analyse<br/>figures, ratios, cash flow"]
  analyse --> similar["find_similar<br/>case cards decided before<br/>the application date"]
  similar --> lenders["match_lenders<br/>hard checks, precedent counts,<br/>cited fit summaries"]
  lenders --> draft["draft_memo<br/>evidence from code + passages"]
  draft --> verify["verify_numbers<br/>every number vs known values"]
  verify -- "unverified numbers<br/>and redrafts < 2" --> draft
  verify --> review{{"human_review<br/>interrupt"}}
  review -- "Request changes<br/>(note)" --> draft
  review -- "Approve" --> finalise["finalise<br/>case → ready"]
  finalise --> done([End])
```

The graph never decides on the loan. "Approve" means the advisor approves the memo text;
the credit decision stays with the advisor and the lender.
