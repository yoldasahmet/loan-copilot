"""Answers (hybrid + rerank): faithfulness and answer relevancy as RAGAS defines them, and the
rate of correct "can't find" replies on unanswerable questions.

The metric definitions follow RAGAS; the judge calls go through llm.py, so they are
pseudonymised and logged in ai_runs (kind `eval_judge`) like every other call.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eval.common import Result, open_case, p95, share, timed
from loancopilot import llm
from loancopilot.embeddings import embed
from loancopilot.ingest import document_label
from loancopilot.models import Document
from loancopilot.retrieval import Scope, format_sources, search
from loancopilot.routes.chat import CANT_FIND, CHAT_TOP_K
from loancopilot.security import case_pseudonymiser

FAITHFULNESS_SCHEMA = llm.strict_schema({
    "type": "object",
    "properties": {"statements": {"type": "array", "items": {
        "type": "object", "properties": {"statement": {"type": "string"},
                                         "supported": {"type": "boolean"}}}}},
})  # fmt: skip
RELEVANCY_SCHEMA = llm.strict_schema({
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "string"}},
                   "noncommittal": {"type": "boolean"}},
})  # fmt: skip


def answer(db: Session, g: dict) -> tuple[str, str]:
    """The chat pipeline for one question, without saving it to the case's chat history.
    Returns (answer, sources text)."""
    case, user = open_case(db, g["company"])
    hits = search(db, g["question"], Scope("case", user=user, case_id=case.id), k=CHAT_TOP_K,
                  rerank=True)  # fmt: skip
    if not hits:
        return CANT_FIND, ""
    documents = db.scalars(select(Document).where(Document.case_id == case.id))
    sources = format_sources(hits, {d.id: document_label(d) for d in documents})
    result = llm.complete(
        kind="chat", prompt=llm.load_prompt("chat"),
        user_content=f"{sources}\n\nQuestion: {g['question']}", case_id=case.id,
        user_id=user.id, source_ids=[str(h.chunk_id) for h in hits],
        pii=case_pseudonymiser(db, case.id), max_tokens=2000,
    )  # fmt: skip
    return result.text.strip(), sources


def faithfulness(db: Session, g: dict, reply: str, sources: str) -> float | None:
    """Share of the answer's statements that the sources support."""
    case, _ = open_case(db, g["company"])
    result = llm.complete(
        kind="eval_judge", prompt=llm.load_prompt("eval_faithfulness"),
        user_content=f"{sources}\n\nQuestion: {g['question']}\n\nAnswer: {reply}",
        case_id=case.id, schema=FAITHFULNESS_SCHEMA, pii=case_pseudonymiser(db, case.id),
        max_tokens=3000,
    )  # fmt: skip
    statements = result.data["statements"]
    return share(sum(s["supported"] for s in statements), len(statements))


def relevancy(db: Session, g: dict, reply: str) -> float:
    """Mean cosine similarity between the question and questions generated from the answer;
    0 for a noncommittal answer."""
    case, _ = open_case(db, g["company"])
    result = llm.complete(
        kind="eval_judge", prompt=llm.load_prompt("eval_relevancy"),
        user_content=f"Answer: {reply}", case_id=case.id, schema=RELEVANCY_SCHEMA,
        pii=case_pseudonymiser(db, case.id), max_tokens=2000,
    )  # fmt: skip
    generated = result.data["questions"]
    if result.data["noncommittal"] or not generated:
        return 0.0
    original, *others = embed([g["question"], *generated])  # normalised: dot = cosine
    return sum(sum(a * b for a, b in zip(original, v, strict=True)) for v in others) / len(others)


def run(db: Session, golden: list[dict]) -> Result:
    rows, latencies = [], []
    for g in golden:
        (reply, sources), ms = timed(answer, db, g)
        latencies.append(ms)
        cant_find = reply == CANT_FIND
        row = {"id": g["id"], "answerable": g["answerable"], "answer": reply,
               "cant_find": cant_find, "faithfulness": None, "relevancy": None}  # fmt: skip
        if g["answerable"] and not cant_find:
            row["faithfulness"] = faithfulness(db, g, reply, sources)
            row["relevancy"] = relevancy(db, g, reply)
        rows.append(row)
    scored = [r for r in rows if r["faithfulness"] is not None]
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    return {
        "faithfulness": share(sum(r["faithfulness"] for r in scored), len(scored)),
        "answer_relevancy": share(sum(r["relevancy"] for r in scored), len(scored)),
        "cant_find_correct": share(sum(r["cant_find"] for r in unanswerable), len(unanswerable)),
        "cant_find_on_answerable": share(sum(r["cant_find"] for r in answerable),
                                         len(answerable)),  # fmt: skip
        "answerable": len(answerable), "unanswerable": len(unanswerable), "scored": len(scored),
        "p95_ms": p95(latencies), "rows": rows,
    }  # fmt: skip
