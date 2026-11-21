# 0006 In-process background tasks instead of a job queue

**Status:** accepted

## Context
Document ingestion and the "prepare application" agent take seconds to minutes. A job queue (Celery, RQ, Arq) adds a broker and a worker process.

## Decision
Use FastAPI `BackgroundTasks`. Progress is persisted in the database (`documents.status`, `prepare_runs.steps`) and the UI polls it. The LangGraph Postgres checkpointer stores agent state, so a run waiting for human review survives restarts.

## Consequences
- One process to run, nothing extra to deploy.
- A restart during ingestion or a running agent step loses that work; the document stays `parsing` or the run `running` and can be retried. A multi-instance deployment would need a real queue.
