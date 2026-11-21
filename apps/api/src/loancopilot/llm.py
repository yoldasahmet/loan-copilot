"""The only module that calls the LLM. Every call is pseudonymised, rate limited and logged
to ai_runs (kind, model, prompt version, tokens, latency, cost, sources, output; no prompts)."""

import json
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
import openai

from loancopilot.config import get_settings
from loancopilot.db import SessionLocal
from loancopilot.models import AiRun
from loancopilot.security import Pseudonymiser
from loancopilot.tracing import span

PROMPTS_DIR = Path(__file__).parent / "prompts"
# Server-side fallback: if the model declines, the API re-runs the request on a
# recommended fallback model inside the same call (routed by refusal category).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
ATTEMPTS = 2  # one retry for an empty or unparseable reply


class LlmError(Exception):
    pass


class RateLimited(LlmError):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


@lru_cache
def load_prompt(name: str) -> Prompt:
    """prompts/{name}.md starts with a `version: ...` line; the rest is the system prompt."""
    first, _, body = (PROMPTS_DIR / f"{name}.md").read_text().partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"prompts/{name}.md must start with a version line")
    return Prompt(name, first.removeprefix("version:").strip(), body.strip())


@dataclass
class LlmResult:
    text: str
    data: Any = None


# ---------------------------------------------------------------- rate limit

_calls: dict[uuid.UUID, deque[float]] = defaultdict(deque)
_calls_lock = threading.Lock()


def check_rate_limit(user_id: uuid.UUID | None) -> None:
    if user_id is None:  # background jobs (ingestion, agent steps) are not user-rate-limited
        return
    limit = get_settings().rate_limit_per_minute
    now = time.monotonic()
    with _calls_lock:
        window = _calls[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            raise RateLimited(
                f"Rate limit reached ({limit} AI requests per minute). Try again soon."
            )
        window.append(now)


# ---------------------------------------------------------------- providers
# Anthropic through its own SDK; OpenAI and OpenRouter through the OpenAI SDK
# (OpenRouter serves the same Chat Completions API at its own base URL).

PROVIDERS = ("anthropic", "openai", "openrouter")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class Request:
    system: str
    user: str
    max_tokens: int
    effort: str
    schema: dict | None


@dataclass
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def provider() -> str:
    """LLM_PROVIDER, or with `auto` the first provider whose API key is set."""
    s = get_settings()
    if s.llm_provider != "auto":
        if s.llm_provider not in PROVIDERS:
            raise LlmError(f"LLM_PROVIDER must be auto or one of {', '.join(PROVIDERS)}.")
        return s.llm_provider
    keys = {"anthropic": s.anthropic_api_key, "openai": s.openai_api_key,
            "openrouter": s.openrouter_api_key}  # fmt: skip
    return next((name for name, key in keys.items() if key), "anthropic")


def _model(name: str) -> str:
    model = get_settings().llm_model
    if name == "openai" and model.startswith("claude"):
        raise LlmError("Set LLM_MODEL to an OpenAI model id in .env.")
    if name == "openrouter" and "/" not in model:
        raise LlmError("Set LLM_MODEL to an OpenRouter model id (provider/model) in .env.")
    return model


@lru_cache
def _anthropic_client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


@lru_cache
def _openai_client(name: str) -> openai.OpenAI:
    s = get_settings()
    key = s.openrouter_api_key if name == "openrouter" else s.openai_api_key
    if not key:
        raise LlmError(NOT_CONFIGURED)
    base_url = OPENROUTER_BASE_URL if name == "openrouter" else None
    return openai.OpenAI(api_key=key, base_url=base_url)


def anthropic_kwargs(req: Request) -> dict[str, Any]:
    output_config: dict[str, Any] = {"effort": req.effort}
    if req.schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": req.schema}
    return {
        "model": _model("anthropic"),
        "max_tokens": req.max_tokens,
        "system": req.system,
        "messages": [{"role": "user", "content": req.user}],
        "output_config": output_config,
        # If the model declines, the API re-runs the request on a recommended fallback model.
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }


def openai_kwargs(req: Request, name: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": _model(name),
        "max_completion_tokens": req.max_tokens,
        "messages": [
            {"role": "system", "content": req.system},
            {"role": "user", "content": req.user},
        ],  # fmt: skip
    }
    if name == "openrouter":  # reasoning models: cap thinking with the same effort level
        kwargs["extra_body"] = {"reasoning": {"effort": req.effort}}
    if req.schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "output", "schema": req.schema, "strict": True},
        }
    return kwargs


def _anthropic_reply(message: Any) -> Reply:
    if message.stop_reason == "refusal":
        raise LlmError("The AI model declined this request.")
    text = "".join(b.text for b in message.content if b.type == "text")
    usage = message.usage
    return Reply(text, message.model, usage.input_tokens, usage.output_tokens)


def _call(req: Request) -> Reply:
    name = provider()
    if name == "anthropic":
        return _anthropic_reply(_anthropic_client().beta.messages.create(**anthropic_kwargs(req)))
    response = _openai_client(name).chat.completions.create(**openai_kwargs(req, name))
    choice = response.choices[0]
    if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
        raise LlmError("The AI model declined this request.")
    tokens_in = response.usage.prompt_tokens if response.usage else 0
    tokens_out = response.usage.completion_tokens if response.usage else 0
    return Reply(choice.message.content or "", response.model, tokens_in, tokens_out)


def _stream_call(req: Request) -> Iterator[str | Reply]:
    """Yields text deltas, then one final Reply with the usage."""
    name = provider()
    if name == "anthropic":
        with _anthropic_client().beta.messages.stream(**anthropic_kwargs(req)) as s:
            yield from s.text_stream
            yield _anthropic_reply(s.get_final_message())
        return
    stream = _openai_client(name).chat.completions.create(
        **openai_kwargs(req, name), stream=True, stream_options={"include_usage": True}
    )
    parts: list[str] = []
    model, tokens_in, tokens_out = _model(name), 0, 0
    for chunk in stream:
        model = chunk.model or model
        if chunk.usage:
            tokens_in, tokens_out = chunk.usage.prompt_tokens, chunk.usage.completion_tokens
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
            yield chunk.choices[0].delta.content
    yield Reply("".join(parts), model, tokens_in, tokens_out)


NOT_CONFIGURED = ("AI is not configured: set ANTHROPIC_API_KEY, OPENAI_API_KEY or "
                  "OPENROUTER_API_KEY in .env.")  # fmt: skip
SDK_ERRORS = (anthropic.AnthropicError, openai.OpenAIError)


# ---------------------------------------------------------------- public API


def _log(*, kind: str, prompt: Prompt, reply: Reply, started: float, case_id: uuid.UUID | None,
         user_id: uuid.UUID | None, source_ids: list[str], output: str) -> None:  # fmt: skip
    settings = get_settings()
    cost = (reply.input_tokens * settings.llm_price_input_per_mtok
            + reply.output_tokens * settings.llm_price_output_per_mtok) / 1_000_000  # fmt: skip
    with SessionLocal() as db:
        db.add(AiRun(
            case_id=case_id, user_id=user_id, kind=kind, model=reply.model,
            prompt_version=prompt.version, input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens, latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=Decimal(str(round(cost, 6))), source_ids=source_ids, output_text=output,
        ))  # fmt: skip
        db.commit()


def complete(*, kind: str, prompt: Prompt, user_content: str, case_id: uuid.UUID | None = None,
             user_id: uuid.UUID | None = None, source_ids: list[str] | None = None,
             schema: dict | None = None, pii: Pseudonymiser | None = None,
             max_tokens: int = 16000, effort: str = "medium") -> LlmResult:  # fmt: skip
    """One non-streaming call. With `schema`, the response is JSON constrained by the API.
    An empty or invalid reply (reasoning models sometimes spend the whole budget thinking) is
    retried once; every attempt is logged."""
    check_rate_limit(user_id)
    pii = pii or Pseudonymiser()
    req = Request(prompt.text, pii.mask(user_content), max_tokens, effort, schema)
    problem = ""
    for _attempt in range(ATTEMPTS):
        started = time.monotonic()
        try:
            with span("llm", kind=kind, prompt_version=prompt.version, provider=provider()):
                reply = _call(req)
        except SDK_ERRORS as exc:
            raise LlmError(f"AI request failed: {exc}") from exc
        except TypeError as exc:  # the Anthropic SDK found no credentials at all
            raise LlmError(NOT_CONFIGURED) from exc
        text = pii.unmask(reply.text)
        _log(kind=kind, prompt=prompt, reply=reply, started=started, case_id=case_id,
             user_id=user_id, source_ids=source_ids or [], output=text)  # fmt: skip
        if not text.strip():
            problem = "The AI returned no text; try again or raise max_tokens."
            continue
        if schema is None:
            return LlmResult(text=text)
        try:
            return LlmResult(text=text, data=json.loads(text))
        except json.JSONDecodeError:  # e.g. cut off at max_tokens
            problem = "The AI response was incomplete; try again or raise max_tokens."
    raise LlmError(problem)


def stream(*, kind: str, prompt: Prompt, user_content: str, case_id: uuid.UUID | None = None,
           user_id: uuid.UUID | None = None, source_ids: list[str] | None = None,
           pii: Pseudonymiser | None = None, max_tokens: int = 16000,
           effort: str = "low") -> Iterator[str]:  # fmt: skip
    """Stream text deltas with placeholders restored; logs the run when the stream ends.
    The rate limit is checked now, before the first chunk is requested."""
    check_rate_limit(user_id)
    pii = pii or Pseudonymiser()
    req = Request(prompt.text, pii.mask(user_content), max_tokens, effort, None)
    log_args = {"kind": kind, "prompt": prompt, "case_id": case_id, "user_id": user_id,
                "source_ids": source_ids or []}  # fmt: skip
    return _stream_and_log(req, pii, log_args)


def _stream_and_log(req: Request, pii: Pseudonymiser, log_args: dict[str, Any]) -> Iterator[str]:
    started = time.monotonic()
    final: list[Reply] = []

    def texts() -> Iterator[str]:
        for item in _stream_call(req):
            if isinstance(item, Reply):
                final.append(item)
            else:
                yield item

    try:
        yield from pii.unmask_stream(texts())
    except SDK_ERRORS as exc:
        raise LlmError(f"AI request failed: {exc}") from exc
    except TypeError as exc:
        raise LlmError(NOT_CONFIGURED) from exc
    reply = final[0]
    _log(**log_args, reply=reply, started=started, output=pii.unmask(reply.text))


def strict_schema(schema: dict) -> dict:
    """Structured outputs need every object closed and every property required."""
    if schema.get("type") == "object" and "properties" in schema:
        schema = {**schema, "additionalProperties": False, "required": list(schema["properties"])}
        schema["properties"] = {k: strict_schema(v) for k, v in schema["properties"].items()}
    if schema.get("type") == "array" and "items" in schema:
        schema = {**schema, "items": strict_schema(schema["items"])}
    return schema
