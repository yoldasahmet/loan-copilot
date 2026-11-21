# SME Loan Copilot — agent notes

Read `docs/spec.md` before larger changes. It is the source of truth; update it when scope changes.

## Hard rules

1. **No data in the public repo.** All example data, demo users, demo documents, golden eval sets and the scripts that create or load them live in `local/`, which is gitignored. A fresh clone is an empty, working app. The only committed artefacts derived from demo data are PNGs in `docs/screenshots/` and the numbers in `docs/eval-results.md`.
2. **Fictional data only.** Never use real client data, real company names, real people or real lenders. Never mention any real employer, client or organisation anywhere in the repo.
3. **Numbers come from code.** Ratios, cash-flow metrics and totals are calculated in Python. The LLM only extracts figures (which code validates) and writes prose. Every number in a memo is checked against known values.
4. **The human decides.** No automated approve/decline, no credit score, no single "fit score". Show facts: criteria checks, precedent counts and cited passages.
5. **Keep the code simple.** Plain functions, one module per concern. No repository/service/manager layers, no DI containers, no generic base classes or plugin systems, no abstraction with only one implementation. Flat over nested, small files, type hints everywhere. Extract a helper only when it has two or more real users.
6. **Secrets** live only in `.env` (gitignored). `.env.example` lists every variable with a one-line comment.
7. **Language:** UI, generated documents and code in English. Money in EUR.

Never weaken, skip or delete a failing test to make it pass.

## Commands

| Command | What it does |
|---|---|
| `docker compose up -d` | Start Postgres + pgvector (port 5433). Add `--profile tracing` for Phoenix on :6006 |
| `make setup` | Install API and web deps, run migrations |
| `make dev` | API on :8000, web on :3000 (web proxies `/api/*` to the API) |
| `make migrate` | Alembic upgrade head |
| `make test` / `make lint` / `make fmt` | pytest + tsc / ruff + Biome / auto-fix |
| `make schema` | Regenerate `docs/import-format.md` |
| `make reindex` | Re-embed all chunks and case cards |
| `make eval EVAL_DIR=local/eval` | Run the evaluation, writes `docs/eval-results.md` |
| `make check-no-data` | Fail if data files are tracked |

## Layout

- `apps/api/src/loancopilot/` — FastAPI app; one module per concern (see spec §5). `llm.py` is the only module that calls the LLM.
- `apps/api/eval/` — eval runner code only; data comes from `EVAL_DIR`.
- `apps/web/src/` — Next.js App Router UI (`app/`, `components/`, `lib/`).
- `docs/` — spec, architecture, ADRs, eval results, screenshots.
- `local/` — gitignored demo data generator, loader and screenshot script.
