# 0001 Postgres-only RAG (pgvector + full-text search)

**Status:** accepted

## Context
The app needs dense vector search, keyword search and ordinary relational data (cases, transactions, decisions). A dedicated vector database would add a second store to run, back up and keep consistent.

## Decision
Use one PostgreSQL 17 database. Dense search uses pgvector with an HNSW index (`vector_cosine_ops`); keyword search uses a generated `tsvector` column with a GIN index and `websearch_to_tsquery`. The two result lists are fused with Reciprocal Rank Fusion in Python.

## Consequences
- One connection, one backup, one transaction boundary. Access control is a `WHERE` clause in the same SQL that does the search, so filtering never happens after retrieval.
- Deletes (right to erasure) are plain cascading deletes.
- At this scale (thousands of chunks) pgvector's HNSW performance is more than enough. A very large corpus might later justify a dedicated engine.
