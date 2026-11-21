"""Cross-encoder reranking (bge-reranker-v2-m3). Skipped when RERANK=off."""

from collections.abc import Sequence
from functools import lru_cache

from loancopilot.config import get_settings


@lru_cache
def _model():  # noqa: ANN202 — heavy import only when reranking is on
    from sentence_transformers import CrossEncoder

    return CrossEncoder(get_settings().reranker_model, device="cpu")


def enabled(override: bool | None = None) -> bool:
    return override if override is not None else get_settings().rerank == "on"


def rerank[T](query: str, items: Sequence[T], texts: Sequence[str], top_k: int) -> list[T]:
    """Order items by cross-encoder score of (query, text); keep top_k."""
    if not items:
        return []
    scores = _model().predict([(query, t) for t in texts], batch_size=16)
    ranked = sorted(zip(items, scores, strict=True), key=lambda pair: -float(pair[1]))
    return [item for item, _ in ranked[:top_k]]
