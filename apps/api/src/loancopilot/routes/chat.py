import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from loancopilot import llm
from loancopilot.auth import DB, CurrentUser, get_case
from loancopilot.db import SessionLocal
from loancopilot.ingest import document_label
from loancopilot.models import ChatMessage, Document
from loancopilot.retrieval import Scope, format_sources, search, source_refs
from loancopilot.security import Pseudonymiser, case_pseudonymiser

router = APIRouter(tags=["chat"])

CANT_FIND = "I can't find this in the case documents."
CHAT_TOP_K = 6
HISTORY_TURNS = 6


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    sources: list[dict[str, Any]]
    created_at: datetime


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _save(case_id: uuid.UUID, user_id: uuid.UUID, role: str, content: str,
          sources: list[dict] | None = None) -> uuid.UUID:  # fmt: skip
    with SessionLocal() as db:
        message = ChatMessage(case_id=case_id, user_id=user_id, role=role, content=content,
                              sources=sources or [])  # fmt: skip
        db.add(message)
        db.commit()
        return message.id


@router.get("/cases/{case_id}/chat")
def chat_history(case_id: uuid.UUID, db: DB, user: CurrentUser) -> list[ChatMessageOut]:
    case = get_case(db, user, case_id)
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.case_id == case.id).order_by(ChatMessage.created_at)
    )
    return [ChatMessageOut.model_validate(m) for m in rows]


def _recent(db: DB, case_id: uuid.UUID) -> list[ChatMessage]:
    query = (
        select(ChatMessage)
        .where(ChatMessage.case_id == case_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_TURNS)
    )
    return list(db.scalars(query))[::-1]


def _standalone_query(question: str, transcript: str, case_id: uuid.UUID,
                      user_id: uuid.UUID, pii: Pseudonymiser) -> str:  # fmt: skip
    """With earlier turns, one short call turns a follow-up into a standalone search query."""
    if not transcript:
        return question
    rewritten = llm.complete(
        kind="query_rewrite",
        prompt=llm.load_prompt("query_rewrite"),
        user_content=f"Conversation:\n{transcript}\n\nLatest question: {question}",
        case_id=case_id, user_id=user_id, pii=pii, max_tokens=200, effort="low",
    )  # fmt: skip
    return rewritten.text.strip() or question


@router.post("/cases/{case_id}/chat")
def ask(case_id: uuid.UUID, body: ChatIn, db: DB, user: CurrentUser) -> StreamingResponse:
    """SSE stream: `token` events, then `sources` (S# → document, page, text), then `done`."""
    case = get_case(db, user, case_id)
    pii = case_pseudonymiser(db, case.id)
    transcript = "\n".join(f"{m.role}: {m.content}" for m in _recent(db, case.id))
    documents = db.scalars(select(Document).where(Document.case_id == case.id))
    labels = {d.id: document_label(d) for d in documents}
    try:
        query = _standalone_query(body.message, transcript, case.id, user.id, pii)
        hits = search(db, query, Scope("case", user=user, case_id=case.id), k=CHAT_TOP_K)
        refs = source_refs(hits)
        tokens: Iterator[str] = iter([CANT_FIND])
        if hits:
            context = f"Conversation so far:\n{transcript}\n\n" if transcript else ""
            content = f"{format_sources(hits, labels)}\n\n{context}Question: {body.message}"
            tokens = llm.stream(
                kind="chat", prompt=llm.load_prompt("chat"), user_content=content,
                case_id=case.id, user_id=user.id, source_ids=[r["chunk_id"] for r in refs],
                pii=pii, max_tokens=2000,
            )  # fmt: skip
    except llm.RateLimited as exc:
        raise HTTPException(429, str(exc)) from exc
    except llm.LlmError as exc:
        raise HTTPException(503, str(exc)) from exc
    _save(case.id, user.id, "user", body.message)

    def events() -> Iterator[str]:
        parts: list[str] = []
        try:
            for token in tokens:
                parts.append(token)
                yield _sse("token", {"text": token})
        except llm.LlmError as exc:
            yield _sse("error", {"message": str(exc)})
            return
        answer = "".join(parts)
        cited = refs if answer.strip() != CANT_FIND else []
        yield _sse("sources", cited)
        message_id = _save(case.id, user.id, "assistant", answer, cited)
        yield _sse("done", {"message_id": str(message_id)})

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
