# 0005 Local embedding and reranker models

**Status:** accepted

## Context
Retrieval needs embeddings and a cross-encoder reranker. Hosted embedding APIs would send every document chunk to a third party and add a second API key.

## Decision
Run `BAAI/bge-m3` (1024-dim, multilingual) and `BAAI/bge-reranker-v2-m3` locally on CPU via sentence-transformers. Model names come from env. `EMBEDDINGS_BACKEND=fake` gives deterministic hash vectors for tests and CI; `RERANK=off` disables the reranker.

## Consequences
- Documents only leave the machine (pseudonymised) for LLM calls.
- First use downloads a few GB of model weights, and CPU inference is slower than an API. Batch size 16 keeps memory reasonable.
- `embedding_model` is stored per row so `make reindex` can re-embed after a model change.
