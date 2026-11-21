"""Optional OpenTelemetry tracing to Arize Phoenix. Off unless PHOENIX_COLLECTOR_ENDPOINT is set."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from functools import lru_cache
from typing import Any

from loancopilot.config import get_settings


@lru_cache
def _tracer() -> Any:
    endpoint = get_settings().phoenix_collector_endpoint
    if not endpoint:
        return None
    from opentelemetry import trace
    from phoenix.otel import register

    register(endpoint=endpoint, project_name="sme-loan-copilot", verbose=False)
    return trace.get_tracer("loancopilot")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """A span around retrieval, reranking, LLM calls and agent nodes (no-op when disabled)."""
    tracer = _tracer()
    if tracer is None:
        with nullcontext():
            yield
        return
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))
        yield
