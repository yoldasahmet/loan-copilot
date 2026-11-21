# SME Loan Copilot — build instructions

You are my coding agent. Build the project described below from scratch in this empty folder.

---

## 0. Context and how to work

**The goal.** This is a **public GitHub portfolio project**. Reviewers will spend a few minutes on it, so it must:

1. solve a believable business problem,
2. look polished in screenshots,
3. show solid RAG engineering with measured results,
4. stay simple to explain.

**How to work**

1. First, save this whole prompt unchanged as `docs/spec.md`. It is the source of truth. If we change scope later, update it.
2. Work through the milestones in section 17 in order. For each milestone: build it, run its "Done when" checks, fix until they pass, commit (Conventional Commits), give me a 3–5 line summary, then continue with the next one.
3. **Pause and wait for my review after M1 (example data) and after M9 (screenshots).** Otherwise keep going.
4. Library APIs change. Before using a library (Docling, LangGraph, pgvector, sentence-transformers, RAGAS, Next.js, shadcn/ui, Playwright, Phoenix), check its current official docs and use the latest stable version. Don't rely on memory for API details.
5. If something is unclear, choose the simplest option that satisfies this spec and mention it in the milestone summary. Ask me only when you need a secret (API key) or a decision that changes scope.
6. Never weaken, skip or delete a failing test to make it pass. Fix the code, or tell me.

---

## 1. The app in 30 seconds

SME Loan Copilot helps loan advisors prepare loan applications for small and medium-sized businesses (SMEs).

An advisor opens a case and uploads the company's annual reports (PDF) and bank statements. The app:

1. extracts the financial figures and calculates ratios,
2. analyses 12 months of bank transactions (cash flow, overdrafts, customer concentration, tax payments),
3. finds the most similar past cases and shows which lenders approved or declined them,
4. lists the lenders that fit, with reasons,
5. drafts a loan memo where every claim cites its source and every number is verified,
6. lets the advisor chat with the case documents.

The advisor reviews, edits and approves. **The app never makes a credit decision and never shows a credit score.**

README version (use this wording or close to it):

> SME Loan Copilot helps loan advisors prepare SME loan applications. Upload a company's annual reports and bank statements; it extracts the figures, analyses cash flow, finds similar past cases and the lenders that approved them, and drafts a cited loan memo. Every number is computed in code and verified, and the advisor makes every decision.

---

## 2. Hard rules (also put these in `CLAUDE.md`)

1. **No data in the public repo.** All example data, demo users, demo documents, golden eval sets and the scripts that create or load them live in `local/`, which is in `.gitignore` from the first commit. Someone who clones the repo gets an **empty, working app** and no way to see demo data. The only things derived from demo data that get committed are the PNG screenshots in `docs/screenshots/` and the numbers in `docs/eval-results.md`.
2. **Fictional data only.** Never use real client data, real company names, real people or real lenders. Never mention any real employer, client or organisation anywhere in the repo. Section 14.1 gives the rules for fictional data.
3. **Numbers come from code.** Ratios, cash-flow metrics and totals are calculated in Python. The LLM only extracts figures (which code then validates) and writes prose. Every number in a memo is checked against known values.
4. **The human decides.** No automated approve/decline, no credit score, no single "fit score". Show facts: criteria checks, precedent counts and cited passages.
5. **Keep the code simple.** Plain functions, one module per concern. No repository/service/manager layers, no dependency-injection containers, no generic base classes or plugin systems, no abstraction that has only one implementation. Prefer flat over nested, small files, type hints everywhere. Don't repeat boilerplate; extract a helper only when there are two or more real users of it.
6. **Secrets** live only in `.env` (gitignored). `.env.example` lists every variable with a one-line comment.
7. **Language:** UI, generated documents and code in English. Money in EUR.

---

## 3. Scope

**In scope:** everything in sections 6–16.

**Out of scope — do not build:** deployment or hosting, OCR for scanned PDFs, MT940 statements, live bank connections (PSD2), KvK API lookups, email or notifications, multiple organisations (tenancy), UI translations, GraphRAG, fine-tuning or training models, any credit score or approve/decline prediction.

---

## 4. Tech stack

| Area | Choice | Notes |
|---|---|---|
| API | Python 3.12+, uv, FastAPI, Pydantic v2 | `apps/api` |
| Database | PostgreSQL 17 + pgvector (`pgvector/pgvector:pg17` image) | One database for everything, including full-text search |
| ORM / migrations | SQLAlchemy 2 (typed models) + Alembic, psycopg 3 | |
| PDF parsing | Docling | Digital PDFs only |
| Bank statements | CAMT.053 XML (stdlib `xml.etree`) and CSV | |
| Embeddings | `BAAI/bge-m3` via sentence-transformers, 1024 dims, CPU | `EMBEDDINGS_BACKEND=fake` for tests and CI |
| Reranker | `BAAI/bge-reranker-v2-m3` via sentence-transformers `CrossEncoder` | Model name in env |
| LLM | Anthropic Claude, OpenAI or OpenRouter (official Anthropic and OpenAI Python SDKs) | Provider in `LLM_PROVIDER` (`auto` picks the first key that is set), model in `LLM_MODEL`; every call goes through `llm.py` |
| Agent | LangGraph with the Postgres checkpointer | |
| Evaluation | Own metric code; faithfulness and answer relevancy follow the RAGAS definitions | The judge calls go through `llm.py` (pseudonymised, logged as `eval_judge`) instead of the `ragas` package |
| Tracing | OpenTelemetry → Arize Phoenix (optional Compose profile `tracing`) | Off when `PHOENIX_COLLECTOR_ENDPOINT` is unset |
| Web | Next.js (App Router), TypeScript, Tailwind, shadcn/ui (including charts), pnpm, Biome | `apps/web` |
| Quality | ruff + pytest (API); Biome + `tsc --noEmit` + `next build` (web) | |
| Dev | Docker Compose, Makefile, GitHub Actions | |

The embedding and reranker models download on first use (a few GB). Say so in the README.

**Environment variables** (`.env.example`): `DATABASE_URL`, `DATA_DIR` (default `./.data`), `SESSION_SECRET`, `LLM_PROVIDER` (`auto` | `anthropic` | `openai` | `openrouter`), `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` (USD, for cost tracking), `EMBEDDINGS_BACKEND` (`local` | `fake`), `EMBEDDING_MODEL`, `RERANK` (`on` | `off`), `RERANKER_MODEL`, `ASSUMED_INTEREST_RATE` (default `0.08`), `RATE_LIMIT_PER_MINUTE` (default `30`), `PHOENIX_COLLECTOR_ENDPOINT` (optional), `API_URL` (used by the Next.js rewrite).

---

## 5. Repository layout

```
sme-loan-copilot/
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   ├── src/loancopilot/
│   │   │   ├── main.py          # FastAPI app, routers mounted under /api
│   │   │   ├── config.py        # settings from env
│   │   │   ├── db.py            # engine, session
│   │   │   ├── models.py        # SQLAlchemy models
│   │   │   ├── auth.py          # sessions, password hashing, allowed_case_ids()
│   │   │   ├── routes/          # auth.py cases.py documents.py analysis.py chat.py prepare.py admin.py
│   │   │   ├── ingest_pdf.py    # Docling → pages, sections, tables
│   │   │   ├── ingest_statements.py  # CAMT.053 + CSV → transactions
│   │   │   ├── chunking.py
│   │   │   ├── embeddings.py
│   │   │   ├── retrieval.py     # dense, keyword, RRF, access filter
│   │   │   ├── rerank.py
│   │   │   ├── llm.py           # the only module that calls the LLM; logs ai_runs
│   │   │   ├── prompts/         # *.md prompt files, each with a version line
│   │   │   ├── extraction.py    # annual-report figures + validation
│   │   │   ├── analysis.py      # ratios, cash flow, red flags, missing documents
│   │   │   ├── history.py       # import format, import, case cards
│   │   │   ├── similar.py       # similar-case search
│   │   │   ├── lenders.py       # hard checks, precedents, fit reasons
│   │   │   ├── memo.py          # memo drafting + number verification
│   │   │   ├── agent.py         # LangGraph "prepare application" graph
│   │   │   ├── security.py      # pseudonymisation, injection scan, upload checks
│   │   │   └── tracing.py       # optional OpenTelemetry setup
│   │   ├── eval/                # eval runner code only — reads data from EVAL_DIR, contains no data
│   │   └── tests/
│   └── web/
│       ├── package.json
│       ├── biome.json
│       └── src/
│           ├── app/             # routes (section 8)
│           ├── components/
│           └── lib/             # api client, formatters
├── docs/
│   ├── spec.md                  # this prompt
│   ├── architecture.md          # Mermaid diagrams
│   ├── import-format.md         # generated from the Pydantic model
│   ├── eval-results.md          # numbers only, written by `make eval`
│   ├── adr/                     # 0001-… short ADRs
│   └── screenshots/             # PNGs only
├── scripts/
│   └── check-no-data.sh
├── local/                       # GITIGNORED — never committed (section 14)
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── .github/workflows/ci.yml
├── CLAUDE.md
├── LICENSE                      # MIT
└── README.md
```

**Makefile targets (public):** `setup` (install deps, run migrations), `dev` (API on :8000 + web on :3000), `migrate`, `test`, `lint`, `fmt`, `schema` (regenerate `docs/import-format.md`), `reindex`, `eval` (requires `EVAL_DIR`), `check-no-data`.

**`.gitignore` must include:** `local/`, `.data/`, `.env`, model caches, `__pycache__`, `.venv`, `node_modules`, `.next`, `eval/results/`.

**`scripts/check-no-data.sh`** fails if `git ls-files` contains anything under `local/`, any file ending in `.pdf .xml .csv .jsonl .xlsx`, or `.env`. It runs in CI and in `make check-no-data`. Tests that need sample input build it inline as strings in the test file.

---

## 6. Data model

Use UUID primary keys, `created_at`/`updated_at` where useful, and `numeric(14,2)` for money.

| Table | Key columns |
|---|---|
| `users` | email (unique), name, password_hash, role (`admin` \| `advisor`) |
| `companies` | name, kvk_number, legal_form (`bv` \| `eenmanszaak` \| `vof` \| `other`), sbi_code, sector_group, founded_year, employees, city, contact_name, contact_email |
| `cases` | company_id, advisor_id, status (`intake` \| `analysing` \| `waiting_review` \| `ready` \| `closed`), loan_amount, loan_purpose (`working_capital` \| `equipment` \| `real_estate` \| `refinancing` \| `growth` \| `other`), loan_term_months, notes, is_historical, applied_on |
| `documents` | case_id (nullable), lender_id (nullable), kind (`annual_report` \| `bank_statement` \| `lender_criteria` \| `other`), filename, sha256, mime, size_bytes, year, page_count, status (`uploaded` \| `parsing` \| `indexed` \| `failed`), error, injection_flag, injection_allowed |
| `chunks` | document_id, case_id, lender_id, kind (`text` \| `table` \| `analysis`), section, page_from, page_to, text, context_header, embedding `vector(1024)`, embedding_model, tsv (generated `tsvector`) |
| `transactions` | case_id, document_id, booked_on, amount (+ in / − out), counterparty_name, counterparty_iban, description, category, balance_after (nullable) |
| `financials` | case_id, year, revenue, cost_of_sales, gross_profit, operating_expenses, ebitda, depreciation, interest_expense, net_income, total_assets, current_assets, cash, equity, current_liabilities, long_term_debt, sources (jsonb: field → document_id + page), warnings (jsonb), edited_by, edited_at; unique (case_id, year) |
| `analyses` | case_id (PK), ratios, cashflow, red_flags, missing_documents (all jsonb), computed_at |
| `lenders` | name, product_type, min_amount, max_amount, min_revenue, min_years_trading, excluded_sector_groups (text[]), allowed_legal_forms (text[]), typical_rate_min, typical_rate_max, active |
| `decisions` | case_id, lender_id, decision (`approved` \| `declined` \| `withdrawn`), amount_granted, interest_rate, term_months, decline_reason, documents_requested (text[]), decided_on |
| `case_cards` | case_id (PK), profile_text, embedding `vector(1024)`, embedding_model, tsv (generated), sector_group, revenue_band, loan_purpose, first_decided_on |
| `prepare_runs` | case_id, status (`running` \| `waiting_review` \| `done` \| `failed`), steps (jsonb: name, status, started_at, finished_at, note), attempt, error |
| `memos` | case_id, version, content_md, sources (jsonb), verification (jsonb), status (`draft` \| `approved` \| `changes_requested`), review_note, approved_by, approved_at |
| `chat_messages` | case_id, user_id, role (`user` \| `assistant`), content, sources (jsonb) |
| `ai_runs` | case_id, user_id, kind (`extraction` \| `query_rewrite` \| `chat` \| `lender_reasons` \| `memo` \| `eval_judge`), model, prompt_version, input_tokens, output_tokens, latency_ms, cost_usd, source_ids (jsonb), output_text (nullable) |

Indexes: HNSW (`vector_cosine_ops`) on `chunks.embedding` and `case_cards.embedding`; GIN on both `tsv` columns (`'english'` config); B-tree on foreign keys and `chunks.kind`. LangGraph's checkpointer creates its own tables.

Revenue bands: `<0.5M`, `0.5–2M`, `2–10M`, `>10M`. Sector groups (10, mapped from the first two digits of the SBI code in a dict): construction, hospitality, retail, wholesale, manufacturing, transport_logistics, it_services, professional_services, healthcare_practices, agriculture.

---

## 7. Users, access and security

- **Roles:** `admin` (all cases, users, lenders, history import, audit log) and `advisor` (only cases where `advisor_id` is them).
- **First run:** if `users` is empty, `/setup` creates the first admin. After that, `/setup` returns 404.
- **Login:** email + password (argon2). The session is a signed, httpOnly cookie (SameSite=Lax; Secure outside localhost) that expires after 8 hours. The web app proxies `/api/*` to FastAPI through a Next.js rewrite, so cookies stay same-origin.
- **Access control:** a single helper `allowed_case_ids(user)` is used by every case, document, chunk, transaction, chat and memo query, **including retrieval (filter in SQL, never after)**. A case the user can't access returns 404, not 403. Historical case cards and lender documents contain no personal data and are visible to all logged-in users.
- **Pseudonymisation before every LLM call:** replace the company name, the contact person, the top 20 counterparty names, IBANs (regex), emails and phone numbers with placeholders (`[COMPANY]`, `[PERSON_1]`, `[COUNTERPARTY_3]`, `[IBAN_2]` …). Restore them in the response before showing or storing it, including placeholders split across streamed chunks. Unit-test this.
- **Prompt injection:** when a document is ingested, scan its chunks against a small pattern list ("ignore previous instructions", "system prompt", "you are now", …). Flag the document (warning badge in the UI) and leave its chunks out of LLM context until an advisor clicks "Allow". Always wrap source text in `<source id="…">` tags, and tell the model to treat it as data, not instructions.
- **Uploads:** allow PDF, XML and CSV only, checked by magic bytes and extension; 20 MB max; files stored at `DATA_DIR/files/{case_id}/{sha256}.{ext}`; served only to users who can access the case. PDFs are served inline so the viewer works.
- **Rate limit:** `RATE_LIMIT_PER_MINUTE` LLM requests per user, kept in memory.
- **Delete case (right to erasure):** removes files, chunks, transactions, financials, analyses, memos, chats, prepare runs and checkpoints. `ai_runs` rows keep their metadata but `output_text` is cleared.
- **Natural-person banner:** for `eenmanszaak` and `vof`, show the banner: "The owner is personally liable, so this assessment concerns a natural person. Take extra care under GDPR and the EU AI Act."
- **Security headers** in Next.js: a basic CSP, `frame-ancestors 'self'` (needed for the PDF iframe), `X-Content-Type-Options`, `Referrer-Policy`.

---

## 8. Screens

**Design direction:** a calm, professional fintech look. shadcn/ui, a left sidebar, light and dark themes, generous spacing, clear typography. These rules matter because the screenshots are the first thing reviewers see:

- Every list has an empty state with a clear next action. Every page has loading skeletons and an error state.
- Money is formatted the same way everywhere: full in tables (`€1,234,567`), compact in cards (`€1.2M`). Dates look like `12 Nov 2026`.
- Each page sets `data-ready="true"` on its root element once its data has loaded (the screenshot script waits for this).
- Layout works from 1024 px wide upwards.

**Pages**

1. **`/setup`** — only when no users exist: create the first admin.
2. **`/login`**
3. **`/` Dashboard**
   - Stat cards: open cases, waiting for review, memos approved this month, average days from intake to ready.
   - Cases table: company, legal form, amount, purpose, status badge, advisor, updated. Search and status filter, plus a "New case" button.
   - Empty state: "No cases yet", with "New case" (and "Import history" for admins).
4. **`/cases/new`** — company details and loan request on one page.
5. **`/cases/[id]`**
   - **Header:** company name, legal-form badge, amount, status, advisor.
   - **"Prepare application" button:** shows progress through the 7 agent steps, with an icon per step.
   - **Natural-person banner** when the legal form needs it.
   - **Tabs:**
     - **Overview** — company and loan details, a summary of red flags, the missing-documents checklist.
     - **Documents** — upload dropzone; list with kind, year, pages, status and injection warning. Clicking a document opens it in a PDF viewer (iframe at the right page).
     - **Analysis**
       - Figures table by year: each value links to its source page, shows warnings, and can be edited inline (an edited value shows "edited by").
       - Ratio cards with green/amber/red colours against the thresholds.
       - Cash-flow chart: monthly in/out bars plus a balance line.
       - Transaction category breakdown and the red-flags list.
     - **Similar cases** — top 5 precedent cards. Each shows the pseudonymous ID (`H-0042`), sector, revenue, loan, similarity-reason chips, and each lender's decision with amount, rate and decline reason.
     - **Lenders** — ranked list. Each lender shows its hard checks (✓/✗), precedent counts ("approved 6 of 8 similar cases"), typical rate range, and a fit summary with citation chips.
     - **Memo**
       - The rendered memo. Citation chips open a source side panel showing the text and an "Open page" link.
       - Unverified numbers are highlighted with a tooltip, and a verification summary bar sits at the top.
       - "Approve" and "Request changes" (with a note) buttons, and a version selector.
   - **Chat** — a right-side sheet that opens from any tab: conversation, streaming answer, citation chips that open the source panel, and 3 suggested questions.
6. **`/admin`** (admins only), with tabs:
   - **Users** — create users, change role, reset password.
   - **Lenders** — create, edit and delete lenders; upload criteria PDFs.
   - **History import** — upload a JSONL file; shows validation errors per line and an import summary.
   - **Audit log** — `ai_runs` table with filters, and a detail drawer showing the sources used.

---

## 9. The RAG pipeline — 13 parts

The README lists these 13 parts with one line each.

**9.1 Ingestion**
- Upload runs a background task (FastAPI `BackgroundTasks`) that moves `documents.status` from `uploaded` → `parsing` → `indexed`, or to `failed` with an error message.
- PDFs go through Docling → per-page structured markdown with tables kept as markdown tables. A PDF with no text layer fails with "Scanned PDFs are not supported."
- CAMT.053 and CSV produce `transactions` rows. CSV columns: `date, amount, counterparty_name, counterparty_iban, description, balance` (balance optional).
- Uploading the same file (same sha256) to the same case does nothing.

**9.2 Chunking**
- Split the Docling output by headings into sections, and keep each table whole as its own `table` chunk.
- Target 200–700 tokens per chunk. Split long sections on paragraph boundaries with about 10% overlap.
- Every chunk stores its section title and page range.
- Build a context header for each chunk, e.g. `Company: … | Document: Annual report 2025 | Section: Directors' report`. Use it for embedding and the keyword index, but don't show it.
- After analysis runs, create one `analysis` chunk per case: plain text generated in code from the ratios, cash-flow metrics and red flags, so chat can answer "what is the DSCR?".
- Transactions are never chunked.

**9.3 Embeddings**
- bge-m3 with normalised vectors, batch size 16. Store `embedding_model` on every row.
- `EMBEDDINGS_BACKEND=fake` gives deterministic hash-based vectors for tests and CI.
- `make reindex` re-embeds everything.

**9.4 Storage**
- Postgres only: pgvector for dense search, a generated `tsvector` for keyword search, normal tables for structured data (see ADR 0001).

**9.5 Retrieval** — `search(query, scope, k, mode, rerank)` in `retrieval.py`
- `scope` is one of: case documents (allowed case IDs), lender documents (lender IDs), or case cards (with filters).
- Dense top 40 + keyword top 40 (`websearch_to_tsquery`), fused with Reciprocal Rank Fusion (k = 60) in Python, then the top 30 go to the reranker.
- In chat, if there is earlier conversation, one short LLM call rewrites the latest question as a standalone search query.
- The access filter goes inside the SQL.
- `mode` (`dense` | `keyword` | `hybrid`) and `rerank` (on/off) exist for the evaluation ablation.

**9.6 Reranking**
- The cross-encoder scores (query, chunk text) pairs for the top 30 and keeps the top 6 for chat and the top 8 for memo questions. Skipped when `RERANK=off`.

**9.7 Generation**
- Sources are numbered `[S1]…[Sn]` and wrapped in `<source>` tags.
- The prompt says: answer only from the sources, cite every factual sentence, and if the sources aren't enough, reply exactly "I can't find this in the case documents."
- Chat streams over SSE. The final event maps S# → document, page and chunk text.
- Prompts are files in `prompts/` with a `version:` line, and the version is logged.

**9.8 Agentic loop** — section 12.

**9.9 Evaluation** — section 15.

**9.10 Observability**
- `llm.py` writes an `ai_runs` row for every LLM call: kind, model, prompt version, tokens, latency, cost (from the env price table), source IDs, output text. Raw prompts are not stored.
- Optional OpenTelemetry spans for retrieve, rerank, LLM calls and each agent node, exported to Phoenix.
- The admin Audit log tab shows all runs.

**9.11 Serving**
- FastAPI under `/api` (section 13) and the Next.js UI (section 8). `make dev` runs both.

**9.12 Security** — section 7.

**9.13 Repo basics**
- Docker Compose, Makefile, CI (lint, tests, check-no-data), ADRs, architecture diagrams, README (section 16).

---

## 10. Financial analysis rules (all in code)

**Extraction**
- The LLM receives the balance-sheet and P&L chunks of one annual report. It returns JSON per field (`value`, `page`) plus the `unit` (`EUR` or `EUR_thousands`; some reports state amounts in thousands in the table header).
- Code then validates:
  1. the displayed number appears on that page (after normalising formats like `1.234.567`, `1,234,567` and `(12,345)` for negatives);
  2. `total_assets ≈ equity + long_term_debt + current_liabilities` (±1%);
  3. `gross_profit ≈ revenue − cost_of_sales` (±1%).
- Failures become `warnings` shown in the UI. Advisor edits are saved with `edited_by`.

**Ratios** (latest year, plus year-over-year where it makes sense)

| Ratio | Formula | Red flag when |
|---|---|---|
| Solvency | equity / total_assets | < 20% |
| Current ratio | current_assets / current_liabilities | < 1.0 |
| EBITDA margin | ebitda / revenue | — |
| Revenue growth | revenue_y / revenue_{y−1} − 1 | < −15% |
| Debt / EBITDA | long_term_debt / ebitda | > 4.0 |
| Interest coverage | ebitda / interest_expense | < 3.0 |
| DSCR | ebitda / (existing annual debt service + new annual debt service) | < 1.25 |

New annual debt service is the annuity on the requested loan at `ASSUMED_INTEREST_RATE` over the requested term. Existing debt service is the sum of `loan_repayment` transactions over the last 12 months. Show the assumption in the UI.

**Cash flow (last 12 months of transactions)**
- Per month: inflow, outflow, net, end-of-month balance (when balances are available).
- Categories come from keyword rules in one dict, matched on counterparty and description: `tax` (Belastingdienst), `salaries`, `loan_repayment`, `rent`, `suppliers`, `customers` (incoming), `bank_fees`, `other`.
- Metrics:
  - average monthly inflow
  - months with negative net cash flow
  - days with a negative balance
  - top customer share (largest single counterparty's share of customer inflow)
  - existing annual debt service
  - tax payments per quarter

**Red flags** (thresholds in one config dict)
- the ratio rules above
- negative balance on more than 10 days
- top customer share above 40%
- any quarter without a tax payment
- company younger than 3 years
- fewer than 2 annual reports

**Missing documents**
- The base checklist: annual reports for the last 2 years and 12 months of statements.
- Plus any document that was requested in at least 30% of the similar cases' decisions and hasn't been uploaded yet.

---

## 11. History, similar cases and lender matching

**History import**
- JSONL, one historical case per line, validated by a Pydantic model `HistoricalCase`:
  - `company` (legal_form, sbi_code, founded_year, employees, region)
  - `application` (applied_on, amount, purpose, term_months)
  - `financials` (list per year with the section 6 fields)
  - `cashflow_summary` (avg_monthly_inflow, negative_balance_days, top_customer_share, existing_annual_debt_service)
  - `decisions` (lender_name, decision, amount_granted, interest_rate, term_months, decline_reason, documents_requested, decided_on)
- The format has **no name fields at all**: history is pseudonymous by design. Imported cases get IDs like `H-0042`.
- `make schema` writes `docs/import-format.md` from the model: a field table and JSON Schema, with placeholder values only.
- Lender names in an import must match existing lenders; unknown names are reported as line errors.

**Case cards**
- `profile_text` is built in code from **profile fields only**: sector, legal form, age, revenue and growth, margins, solvency, cash-flow summary, loan amount, purpose and term. Outcomes are **never** embedded. They are stored in `decisions` and only displayed.
- Open cases build the same profile text when they're searched.

**Similar-case search**
- Hybrid search plus rerank over `case_cards`, with the filter `first_decided_on < case.applied_on` (no leakage). Top 5.
- Similarity reasons are computed in code: same sector group, revenue within ±30%, solvency difference, same loan purpose, similar age.

**Lender matching** (all active lenders)
1. **Hard checks** in code: amount range, minimum revenue, minimum years trading, excluded sector groups, allowed legal forms. Each check shows ✓/✗ with the value.
2. **Precedents:** among the top 20 similar cases, count this lender's decisions ("approved X of Y") and the median granted/requested ratio.
3. **Criteria passages:** retrieve the top 2 chunks from this lender's criteria documents for the case profile.
4. **Fit summary:** one LLM call for all lenders writes a 1–2 sentence summary per lender, citing the passages.
5. **Ranking:** lenders that fail a hard check go last. The rest are ordered by approved/decided ratio when Y ≥ 3, then by Y. Show the counts, never a single score.

---

## 12. "Prepare application" agent and memo

A LangGraph graph with the Postgres checkpointer. `thread_id` = `{case_id}:{run_number}`. It runs as a background task, and every node updates `prepare_runs.steps`. The UI polls `GET /api/cases/{id}/prepare` every 2 seconds.

```
check_documents → analyse → find_similar → match_lenders → draft_memo → verify_numbers ─┬→ human_review → finalise
                                                                  ↑                      │
                                                                  └── redraft (max 2) ───┘
```

1. **check_documents** — computes missing documents. It continues anyway and records them.
2. **analyse** — runs extraction for any annual report that hasn't been extracted yet, then the analysis (plain function calls).
3. **find_similar** — top 5 precedents.
4. **match_lenders** — section 11.
5. **draft_memo**
   - **Input:** all evidence as numbered sources `[S1…Sn]`, each with a type:
     - `document` passages: the top passages for 4 fixed questions (business description, revenue development, main risks, purpose of the loan)
     - `figure` (financials)
     - `metric` (ratios and cash flow)
     - `precedent` (similar case)
     - `lender` (match result)
   - **Sections:** Summary · Company · Loan request · Financial analysis · Cash flow · Risks and mitigants · Similar cases · Lender options · Missing documents.
   - Every factual sentence cites at least one source.
   - **No recommendation to approve or decline.** The memo presents options and facts.
6. **verify_numbers** — code extracts every number in the memo (formats: `€1.2M`, `€450k`, `1,234,567`, `12.5%`, `1.35x`, years excluded) and checks it against the numbers in the sources and figures. A number passes if it matches exactly or within display rounding (±1%). Unverified numbers are listed. If there are any and `attempt < 2`, go back to `draft_memo` with the list as feedback.
7. **human_review** — a LangGraph `interrupt`. Run status becomes `waiting_review` and the case moves to `waiting_review`.
   - "Approve" sets memo `approved` and case `ready`.
   - "Request changes" with a note resumes the graph to `draft_memo` with the note, and saves a new memo version.
8. **finalise** — closes the run.

---

## 13. API (all under `/api`, JSON unless noted)

- **Health:** `GET /health`
- **Auth:** `POST /auth/setup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
- **Cases:** `GET /cases` (search, status filter), `POST /cases`, `GET /cases/{id}`, `PATCH /cases/{id}`, `DELETE /cases/{id}`
- **Documents:** `POST /cases/{id}/documents` (multipart), `GET /cases/{id}/documents`, `GET /documents/{id}/file`, `POST /documents/{id}/allow` (injection override), `DELETE /documents/{id}`
- **Analysis:** `GET /cases/{id}/analysis`, `POST /cases/{id}/analysis/run`, `PATCH /cases/{id}/financials/{year}`
- **Similar and lenders:** `GET /cases/{id}/similar`, `GET /cases/{id}/lenders`
- **Prepare:** `POST /cases/{id}/prepare`, `GET /cases/{id}/prepare`, `POST /cases/{id}/memo/approve`, `POST /cases/{id}/memo/request-changes`
- **Memo:** `GET /cases/{id}/memo?version=`
- **Chat:** `GET /cases/{id}/chat`, `POST /cases/{id}/chat` (SSE stream: `token` events, then a `sources` event, then `done`)
- **Admin:**
  - Users: `GET|POST /admin/users`, `PATCH /admin/users/{id}`
  - Lenders: `GET|POST /admin/lenders`, `PATCH|DELETE /admin/lenders/{id}`, `POST /admin/lenders/{id}/documents`
  - History: `POST /admin/history/import` (JSONL upload → per-line result)
  - Audit: `GET /admin/audit`

Use Pydantic schemas for every request and response. FastAPI's OpenAPI docs stay enabled at `/api/docs`.

---

## 14. Local example data — `local/` (never committed)

Everything in this section lives in `local/`, which is gitignored. It has its own `pyproject.toml` (uv) and `Makefile`, plus `local/README.md` explaining the commands. It talks to the app **only through its HTTP API**, so loading demo data exercises the real code paths.

```
local/
├── README.md
├── Makefile          # generate, load, reset, screenshots
├── pyproject.toml
├── .env              # DEMO_PASSWORD, API_URL
├── seed/
│   ├── generate.py   # writes data/ and eval/ — fixed seed 42, deterministic
│   ├── templates/    # HTML templates for annual reports and lender criteria
│   ├── load.py       # loads everything through the API
│   └── screenshots.py
├── data/             # generated
└── eval/             # generated golden sets
```

### 14.1 Fictional-data rules (strict)

- **Company names:** invented from made-up stems + trade + legal form. Check them against a denylist of ~50 well-known Dutch company and bank names, and regenerate on a match.
- **Lenders:** invented names. Never real banks or lenders.
- **People:** Faker `nl_NL` names; emails at `example.com`.
- **IBANs:** format `NLkk DEMO 0xxxxxxxxx` with **valid check digits**. `DEMO` is not a real bank code, so they look real but can't exist.
- **KvK numbers:** random 8 digits. **No BSN anywhere.**
- **Every generated PDF** has a small footer: "Synthetic demo document — fictional company."
- **Internally consistent figures:**
  - Balance sheets balance and P&L lines add up.
  - Customer inflows over 12 months roughly match revenue (±10%).
  - Tax and loan repayments appear in the statements.
  - Overdrafts appear where the story says so.

### 14.2 What `make -C local generate` creates

- **Users:** 1 admin and 3 advisors (password `DEMO_PASSWORD`). The 3rd advisor gets no cases, for the empty-state screenshot.
- **Lenders:** 6 fictional lenders, one per product type: bank-style term loan, alternative lender, crowdfunding platform, equipment lease, invoice finance, regional growth fund. Each has:
  - structured criteria matching the `lenders` table,
  - a 2–3 page criteria PDF in prose: eligibility, typical rates, required documents, sectors they avoid.
- **`data/history.jsonl`:** 240 historical cases with applications between Jan 2021 and Sep 2026.
  - Spread across the 10 sector groups and all revenue bands; legal forms about 60% BV, 30% eenmanszaak, 10% VOF.
  - Each case has 1–3 lender decisions.
  - Decisions follow each lender's hard criteria plus a probability based on solvency, DSCR, revenue growth and red flags, with noise. This way precedents carry real signal for the backtest.
  - Granted amounts are 60–100% of the request; rates fall within the lender's range, adjusted for risk.
- **5 demo cases** (open), each with:
  - company details and a contact person
  - a loan request
  - annual reports for 2024 and 2025: PDF, 5–7 pages (cover, directors' report, balance sheet, P&L, notes, compilation statement)
  - a CAMT.053 statement for Nov 2025 – Oct 2026
  - an assigned advisor

  Use 3 different report layouts across the demo cases, and state amounts in € thousands in one of them. Write the true figures for every demo report to `data/cases/truth.json` (used by the M4 check).
- **`eval/golden_retrieval.jsonl`:** about 50 questions over demo cases 1–4.
  - Each planted fact in a directors' report or the notes (reason for the revenue change, employee count, largest investment, main customer dependency, seasonality, outlook, a new location, lease obligations) gets 2 paraphrased questions, worded differently from the text.
  - Each question records its expected document and page.
  - Add 5 unanswerable questions, where the expected answer is the can't-find message.
- **`eval/extraction/`:** 20 extra annual-report PDFs in all 3 layouts, plus `truth.json` with the true figures. These are not loaded into the app.
- **Injection test document:** one `other` document for demo case 3 containing a hidden prompt-injection sentence, to show the warning badge.

### 14.3 Demo case stories

| # | Profile | Legal form | Request | What the screenshots show |
|---|---|---|---|---|
| 1 | Installation contractor, 12 years, revenue ≈ €3.4M (+12%), solvency ≈ 38% | BV | €450k, equipment, 60 months | Healthy case: strong precedents, 3 lenders fit, approved memo |
| 2 | Seasonal restaurant, 7 years, revenue ≈ €0.9M, overdraft Nov–Mar | Eenmanszaak | €120k, renovation, 48 months | Natural-person banner, overdraft red flag, seasonal cash-flow chart |
| 3 | IT services, 5 years, revenue ≈ €1.8M, top customer ≈ 55% of inflow | BV | €250k, working capital, 36 months | Concentration red flag, injection-flagged document |
| 4 | Retail, 3 shops, 15 years, revenue −22%, solvency ≈ 14% | VOF | €300k, refinancing, 60 months | Decline and DSCR red flags, mostly declined precedents, memo waiting for review |
| 5 | E-commerce, 2 years, only one annual report | BV | €150k, growth, 36 months | Missing documents, young-company flag, not prepared yet |

### 14.4 `make -C local load` (the app must be running)

1. `/auth/setup` the admin, then create the advisors.
2. Create the lenders and upload their criteria PDFs.
3. Import `history.jsonl` and assert 240 imported, 0 errors.
4. Create the 5 demo cases and upload their documents. Wait until everything is `indexed`.
5. Run analysis on all 5 cases, then "Prepare application" on cases 1–4.
6. Approve case 1's memo. Leave cases 2–4 `waiting_review`.
7. Ask 3 chat questions on case 1 and 2 on case 2.

`make -C local reset` drops the database and `.data/`, runs migrations, then loads again.

### 14.5 `make -C local screenshots`

- Python Playwright. Viewport 1440×900, device scale factor 2, light and dark (`color_scheme`). Inject CSS that disables animations and transitions, and wait for `[data-ready="true"]` and network idle.
- Log in as advisor 1 (and as the admin for admin pages). Save to `docs/screenshots/{nn}-{name}-{light|dark}.png`.
- Screens:
  1. dashboard
  2. empty dashboard (advisor 3)
  3. case 1 overview with completed prepare progress
  4. case 1 documents
  5. case 2 analysis (cash-flow chart)
  6. case 4 similar cases
  7. case 1 lenders
  8. case 4 memo with the source panel open and one number highlighted (if none is unverified, show the verification bar)
  9. case 1 chat with sources
  10. case 3 documents with the injection warning
  11. admin audit log
- After capturing, open every image and check it for layout bugs, cut-off text and anything that doesn't look fictional. Fix the UI and recapture if needed.

---

## 15. Evaluation

The eval code is public in `apps/api/eval/`, but the data comes from `EVAL_DIR` (`make eval EVAL_DIR=local/eval`). It runs against the local database loaded by `make -C local load`. It writes `docs/eval-results.md` (tables, config, date, model names) and raw JSON to `eval/results/` (gitignored). **CI never runs the eval** because there is no data in CI. Without a working LLM the eval still runs retrieval, the backtest and memo verification, and marks the answer and extraction parts as not run.

1. **Retrieval:** recall@5 and MRR@10 on the golden questions for 4 configurations: `dense`, `keyword`, `hybrid`, `hybrid + rerank`.
2. **Answers** (hybrid + rerank): faithfulness and answer relevancy as RAGAS defines them (computed in `apps/api/eval/`, judged through `llm.py`), plus the rate of correct "can't find" replies on the unanswerable questions.
3. **Extraction:** field-level accuracy (within 0.5%) on the 20 extraction PDFs, and the share of reports that raised validation warnings.
4. **Backtest:**
   - Hold out the historical cases that applied in the last 12 months. For each one, only cases decided before its application date are searchable.
   - **Lender hit@3:** does an approving lender appear in the top 3 of the lender ranking? (Only cases with at least one approval.)
   - **Precedent agreement:** does the majority outcome of the top 5 similar cases match the actual first decision?
   - **Amount coverage:** is the granted amount within the 25th–75th percentile of approved amounts in similar cases?
   - Compare against two baselines: random lender order and "most popular lender first".
5. **Memo verification:** share of memos where every number is verified on the first draft, and after redrafting.

`docs/eval-results.md` starts with one summary table:

| Pipeline | Recall@5 | MRR@10 | Faithfulness | p95 latency |
|---|---|---|---|---|
| Dense only | … | … | — | … |
| Keyword only | … | … | — | … |
| Hybrid (RRF) | … | … | — | … |
| Hybrid + rerank | … | … | … | … |

Then the extraction, backtest (with baselines) and memo-verification tables, and a short "How to read this" paragraph.

---

## 16. README and docs

**README order**

1. Title and the 3-sentence explanation from section 1.
2. Screenshot gallery: dashboard, analysis, memo and chat (light), with a link to `docs/screenshots/` for the rest.
3. Features (6 bullets).
4. Architecture diagram (Mermaid).
5. "How the RAG pipeline works": the 13 parts, one line each.
6. Evaluation results: the summary table from `docs/eval-results.md`, plus the backtest headline numbers.
7. Privacy and compliance by design:
   - human-in-the-loop, no credit scoring
   - numbers from code and verified
   - pseudonymisation before LLM calls
   - access control in retrieval
   - natural-person banner
   - erasure on delete
   - injection flagging

   End with "This is a portfolio project, not legal advice."
8. Quickstart for an empty app, plus requirements: Docker, Python 3.12 + uv, Node + pnpm, an Anthropic, OpenAI or OpenRouter API key, disk space for models.
9. Importing your own historical cases (link to `docs/import-format.md`).
10. Tech stack.
11. The note: "All data shown in screenshots is synthetic. Companies, people, lenders and figures are fictional."
12. License (MIT).

**`docs/architecture.md`:** Mermaid diagrams for (a) the system (web, API, Postgres, models, LLM, Phoenix) and (b) the ingestion → retrieval → generation flow plus the agent graph.

**ADRs** (`docs/adr/`, half a page each):
- 0001 Postgres-only RAG (pgvector + full-text search) instead of a vector DB
- 0002 Numbers computed in code; LLM extracts and writes prose only
- 0003 Human-in-the-loop, no credit scoring (EU AI Act, GDPR Art. 22)
- 0004 Demo data lives only in a local, gitignored folder
- 0005 Local embedding and reranker models
- 0006 In-process background tasks instead of a job queue (simplicity trade-off)

**`CLAUDE.md`:** the hard rules from section 2, the commands (`make …`), the repo layout in short, and "read `docs/spec.md` before larger changes".

---

## 17. Milestones

**M0 — Skeleton and guardrails**
- Build: the layout from section 5, `.gitignore`, `.env.example`, Docker Compose (db; Phoenix under the `tracing` profile), Makefile, `CLAUDE.md`, `docs/spec.md`, ADR files, CI workflow (lint + tests for both apps + `check-no-data`), `GET /api/health`, a Next.js shell with sidebar and theme toggle, and the `/api` rewrite.
- Done when:
  - `docker compose up -d && make setup && make dev` serves the shell on :3000, and `/api/health` returns ok through the web origin;
  - `make lint test check-no-data` passes;
  - `git check-ignore -v local/anything` confirms `local/` is ignored.

**M1 — Local example data generator (`local/` only)**
- Build: section 14.1–14.3 (`generate.py`, HTML templates, PDF rendering with Playwright `page.pdf()`).
- Done when:
  - two runs of `make -C local generate` produce identical structured files;
  - all balance sheets balance and all IBANs validate;
  - you render pages 1 and 3 of three different demo PDFs to PNG and show them to me;
  - `git status` shows nothing from `local/`.
- **→ Pause for my review.**

**M2 — Auth, users, cases, documents (no AI yet)**
- Build: models + the first Alembic migration; setup/login/logout/me; `allowed_case_ids`; cases CRUD; validated uploads and file storage; the dashboard, new-case page, case header, Documents tab and admin Users tab.
- Done when:
  - on a fresh database, the flow `/setup` → admin → create advisor → advisor creates a case and uploads a PDF works;
  - tests prove advisor B gets 404 on advisor A's case and files.

**M3 — Ingestion, chunking, embeddings, storage**
- Build: Docling parsing → sections and table chunks with pages; the CAMT.053/CSV parsers; embeddings and indexes; `make reindex`; document status in the UI.
- Done when:
  - a demo annual report produces sensible section and table chunks with correct page numbers;
  - a statement produces transactions;
  - re-uploading the same file does nothing;
  - unit tests cover the chunker and both parsers (with inline fixture strings).

**M4 — Analysis**
- Build: section 10 (extraction + validation, figure editing, ratios, cash flow, categories, red flags, missing documents, the analysis chunk), plus the Analysis and Overview tabs.
- Done when:
  - figures for all 5 demo cases match the generator's truth;
  - unit tests cover every ratio, the annuity and DSCR, every red-flag threshold, and number normalisation (including the € thousands unit).

**M5 — Retrieval, reranking, chat**
- Build: `search()`, RRF, rerank, query rewrite, cited generation, SSE streaming, pseudonymisation, the source panel, chat history, the rate limit.
- Done when:
  - chat answers 5 planted-fact questions on demo case 1 with correct citations;
  - an unanswerable question returns the can't-find message;
  - pseudonymise/restore tests pass, including a placeholder split across stream chunks;
  - a test proves retrieval never returns chunks from another advisor's case.

**M6 — History, similar cases, lenders**
- Build: the import endpoint and admin tab, `make schema`, case cards, similar-case search with the leakage filter, lender CRUD with criteria docs, hard checks, precedent counts, fit summaries, the Similar cases and Lenders tabs, missing documents from precedents.
- Done when:
  - importing `history.jsonl` reports 240 imported / 0 errors, and a broken line gives a clear error;
  - demo case 4 shows mostly declined precedents;
  - hard checks are unit-tested.

**M7 — Agent, memo, audit, tracing**
- Build: section 12 (graph, checkpointer, interrupt, progress, memo with sources, number verifier with the redraft loop, review actions, versions), `ai_runs` logging for every LLM call, optional Phoenix tracing, the Audit log tab.
- Done when:
  - "Prepare application" on demo case 1 reaches `waiting_review` and the memo has all sections with working citations;
  - the verifier is unit-tested on every number format in section 12;
  - "Request changes" produces a new version that addresses the note, and "Approve" sets the case to `ready`;
  - the audit log shows every call with tokens and latency.

**M8 — Security hardening**
- Build: injection scan + the allow flow, magic-byte checks, erasure on delete, security headers, the natural-person banner, and a review that every query uses `allowed_case_ids`.
- Done when:
  - tests cover injection flagging, erasure (nothing left in tables or files) and upload rejection;
  - demo case 3's injection document is flagged.

**M9 — Loader and screenshots (`local/`)**
- Build: section 14.4–14.5.
- Done when:
  - `make -C local reset load screenshots` runs end to end;
  - `docs/screenshots/` has every screen in light and dark, and you have reviewed each image;
  - only PNGs are added to git.
- **→ Pause for my review.**

**M10 — Evaluation, README, polish**
- Build: the eval runner (section 15) run against the local data, `docs/eval-results.md`, the README and architecture docs (section 16), final clean-up.
- Done when: the section 18 checklist passes.

---

## 18. Final checklist

- [ ] A fresh clone in a new folder: `cp .env.example .env` (add an API key) → `docker compose up -d` → `make setup` → `make dev` gives an **empty** app. `/setup` works, there are no errors, and no data appears anywhere.
- [ ] `git ls-files` contains nothing from `local/` and no PDF, XML, CSV, JSONL or `.env` files; `check-no-data` passes in CI.
- [ ] CI is green.
- [ ] The README has the 3-sentence explanation, screenshots, the 13 parts, the eval table, the quickstart and the synthetic-data note.
- [ ] Every screen has empty, loading and error states.
- [ ] No TODOs, dead code or unused files.
- [ ] The code follows the simplicity rule (section 2, rule 5).
