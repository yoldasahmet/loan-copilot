# 0004 Demo data lives only in a local, gitignored folder

**Status:** accepted

## Context
This is a public repository. Demo data that looks realistic can be mistaken for real data, and committing generators makes it easy to blur the line.

## Decision
Everything that creates, contains or loads demo data — users, companies, documents, history, golden eval sets — lives in `local/`, which is gitignored from the first commit. The loader talks to the app only through its HTTP API. `scripts/check-no-data.sh` fails CI if any `local/` file, PDF, XML, CSV, JSONL, XLSX or `.env` file is tracked. Tests build their fixtures inline as strings.

## Consequences
- A fresh clone is an empty, working app.
- The only committed artefacts derived from demo data are screenshots and eval numbers.
- The eval cannot run in CI; it runs locally with `make eval EVAL_DIR=local/eval`.
