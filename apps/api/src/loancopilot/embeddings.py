"""Embeddings: bge-m3 via sentence-transformers, or deterministic hash vectors for tests/CI.

`python -m loancopilot.embeddings` re-embeds every chunk and case card (make reindex).
"""

import hashlib
import math
import re
from functools import lru_cache

from loancopilot.config import get_settings
from loancopilot.models import EMBEDDING_DIM

BATCH_SIZE = 16


def model_name() -> str:
    settings = get_settings()
    return "fake-hash-v1" if settings.embeddings_backend == "fake" else settings.embedding_model


@lru_cache
def _model():  # noqa: ANN202 — heavy import only when the local backend is used
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model, device="cpu")


def _fake(text: str) -> list[float]:
    """Hashed bag of words: deterministic, normalised, and similar texts get similar vectors."""
    vec = [0.0] * EMBEDDING_DIM
    for word in re.findall(r"\w+", text.lower()):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        vec[int.from_bytes(digest[:4], "big") % EMBEDDING_DIM] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if get_settings().embeddings_backend == "fake":
        return [_fake(t) for t in texts]
    vectors = _model().encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True,
                              convert_to_numpy=True)  # fmt: skip
    return [v.tolist() for v in vectors]


def reindex() -> None:
    from sqlalchemy import select

    from loancopilot.db import SessionLocal
    from loancopilot.models import CaseCard, Chunk

    with SessionLocal() as db:
        chunks = list(db.scalars(select(Chunk)))
        for start in range(0, len(chunks), 256):
            batch = chunks[start : start + 256]
            vectors = embed([f"{c.context_header}\n{c.text}" for c in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding, chunk.embedding_model = vector, model_name()
            db.commit()
        cards = list(db.scalars(select(CaseCard)))
        for card, vector in zip(cards, embed([c.profile_text for c in cards]), strict=True):
            card.embedding, card.embedding_model = vector, model_name()
        db.commit()
        print(f"Re-embedded {len(chunks)} chunks and {len(cards)} case cards with {model_name()}")


if __name__ == "__main__":
    reindex()
