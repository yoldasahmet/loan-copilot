"""Hybrid retrieval over chunks: dense (pgvector) + keyword (tsvector), fused with RRF,
then optionally reranked. The access filter is part of the SQL, never applied afterwards."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from loancopilot import rerank as reranker
from loancopilot.auth import allowed_case_ids
from loancopilot.embeddings import embed
from loancopilot.models import CaseCard, Chunk, Document, User

Mode = Literal["dense", "keyword", "hybrid"]
CANDIDATES = 40  # per retriever
RERANK_POOL = 30
RRF_K = 60


@dataclass(frozen=True)
class Scope:
    """What may be searched. `user` is required for case documents (access control)."""

    kind: Literal["case", "lender"]
    user: User | None = None
    case_id: uuid.UUID | None = None
    lender_ids: tuple[uuid.UUID, ...] = ()


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID | None
    filename: str | None
    kind: str
    section: str | None
    page_from: int | None
    page_to: int | None
    text: str
    score: float


def _filters(scope: Scope) -> list[ColumnElement[bool]]:
    # Documents flagged for prompt injection stay out of LLM context until an advisor allows them.
    safe_documents = select(Document.id).where(
        or_(Document.injection_flag.is_(False), Document.injection_allowed.is_(True))
    )
    clauses = [or_(Chunk.document_id.is_(None), Chunk.document_id.in_(safe_documents))]
    if scope.kind == "case":
        if scope.user is None or scope.case_id is None:
            raise ValueError("case scope needs a user and a case_id")
        clauses += [Chunk.case_id == scope.case_id,
                    Chunk.case_id.in_(allowed_case_ids(scope.user))]  # fmt: skip
    else:
        clauses.append(Chunk.lender_id.in_(scope.lender_ids))
    return clauses


def keyword_query(text: str) -> str:
    """websearch_to_tsquery ANDs all words; a question rarely contains them all, so OR them."""
    words = re.findall(r"[\w'-]{2,}", text.lower())
    return " or ".join(dict.fromkeys(words))


def _dense(db: Session, id_col: Any, embedding_col: Any, filters: Sequence[Any], query: str,
           n: int) -> list[uuid.UUID]:  # fmt: skip
    vector = embed([query])[0]
    stmt = select(id_col).where(*filters, embedding_col.is_not(None))
    return list(db.scalars(stmt.order_by(embedding_col.cosine_distance(vector)).limit(n)))


def _keyword(db: Session, id_col: Any, tsv_col: Any, filters: Sequence[Any], query: str,
             n: int) -> list[uuid.UUID]:  # fmt: skip
    tsquery = func.websearch_to_tsquery("english", keyword_query(query))
    stmt = select(id_col).where(*filters, tsv_col.op("@@")(tsquery))
    return list(db.scalars(stmt.order_by(func.ts_rank_cd(tsv_col, tsquery).desc()).limit(n)))


def dense_ids(db: Session, query: str, scope: Scope, n: int = CANDIDATES) -> list[uuid.UUID]:
    return _dense(db, Chunk.id, Chunk.embedding, _filters(scope), query, n)


def keyword_ids(db: Session, query: str, scope: Scope, n: int = CANDIDATES) -> list[uuid.UUID]:
    return _keyword(db, Chunk.id, Chunk.tsv, _filters(scope), query, n)


def rrf(rankings: list[list[uuid.UUID]], k: int = RRF_K) -> list[tuple[uuid.UUID, float]]:
    """Reciprocal Rank Fusion: score = Σ 1 / (k + rank)."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def search(db: Session, query: str, scope: Scope, k: int = 6, mode: Mode = "hybrid",
           rerank: bool | None = None) -> list[Hit]:  # fmt: skip
    rankings = []
    if mode in ("dense", "hybrid"):
        rankings.append(dense_ids(db, query, scope))
    if mode in ("keyword", "hybrid"):
        rankings.append(keyword_ids(db, query, scope))
    fused = rrf(rankings)[:RERANK_POOL]
    if not fused:
        return []
    chunk_ids = [chunk_id for chunk_id, _ in fused]
    rows = {c.id: c for c in db.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))}
    document_ids = {c.document_id for c in rows.values() if c.document_id}
    names = {
        doc_id: filename
        for doc_id, filename in db.execute(
            select(Document.id, Document.filename).where(Document.id.in_(document_ids))
        )
    }
    hits = []
    for chunk_id, score in fused:
        c = rows[chunk_id]
        hits.append(Hit(c.id, c.document_id, names.get(c.document_id), c.kind, c.section,
                        c.page_from, c.page_to, c.text, score))  # fmt: skip
    if reranker.enabled(rerank):
        return reranker.rerank(query, hits, [f"{h.section or ''}\n{h.text}" for h in hits], k)
    return hits[:k]


def format_sources(hits: list[Hit], labels: dict[uuid.UUID, str] | None = None) -> str:
    """Number hits S1..Sn inside <source> tags (the prompt says: data, not instructions)."""
    blocks = []
    for i, h in enumerate(hits, start=1):
        doc = (labels or {}).get(h.document_id) if h.document_id else None
        attrs = f'id="S{i}" document="{doc or h.filename or h.section or h.kind}"'
        if h.page_from:
            attrs += f' page="{h.page_from}"'
        blocks.append(f"<source {attrs}>\n{h.text}\n</source>")
    return "\n\n".join(blocks)


def source_refs(hits: list[Hit]) -> list[dict]:
    """What the UI needs to show a citation: S# → document, pages and the chunk text."""
    return [
        {"id": f"S{i}", "chunk_id": str(h.chunk_id),
         "document_id": str(h.document_id) if h.document_id else None,
         "filename": h.filename or ("Financial analysis" if h.kind == "analysis" else None),
         "section": h.section, "page_from": h.page_from, "page_to": h.page_to, "text": h.text}
        for i, h in enumerate(hits, start=1)
    ]  # fmt: skip


# ---------------------------------------------------------------- case cards (similar cases)


def search_cards(db: Session, query: str, before: date, k: int = 5, mode: Mode = "hybrid",
                 rerank: bool | None = None) -> list[uuid.UUID]:  # fmt: skip
    """Historical case cards decided before `before` (no leakage), best first."""
    eligible = [CaseCard.first_decided_on < before]
    rankings = []
    if mode in ("dense", "hybrid"):
        rankings.append(_dense(db, CaseCard.case_id, CaseCard.embedding, eligible, query,
                               CANDIDATES))  # fmt: skip
    if mode in ("keyword", "hybrid"):
        rankings.append(_keyword(db, CaseCard.case_id, CaseCard.tsv, eligible, query, CANDIDATES))
    pool = [case_id for case_id, _ in rrf(rankings)[:RERANK_POOL]]
    if not reranker.enabled(rerank) or not pool:
        return pool[:k]
    rows = db.execute(select(CaseCard.case_id, CaseCard.profile_text)
                      .where(CaseCard.case_id.in_(pool)))  # fmt: skip
    texts = {case_id: text for case_id, text in rows}
    return reranker.rerank(query, pool, [texts[c] for c in pool], k)
