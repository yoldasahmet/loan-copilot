"""The "prepare application" agent: a LangGraph graph with the Postgres checkpointer.

check_documents → analyse → find_similar → match_lenders → draft_memo → verify_numbers
  → (redraft, max 2) → human_review (interrupt) → finalise, or back to draft_memo on
"request changes". thread_id = "{case_id}:{run_number}". Every node updates prepare_runs.steps.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache, wraps
from typing import Any, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loancopilot import memo as memos
from loancopilot.analysis import compute_cashflow, missing_documents, run_analysis
from loancopilot.config import get_settings
from loancopilot.db import SessionLocal
from loancopilot.lenders import match_lenders
from loancopilot.models import Analysis, Case, Document, Memo, PrepareRun, Transaction
from loancopilot.similar import similar_cases
from loancopilot.tracing import span

log = logging.getLogger(__name__)

STEPS = [
    ("check_documents", "Check documents"),
    ("analyse", "Analyse figures and cash flow"),
    ("find_similar", "Find similar cases"),
    ("match_lenders", "Match lenders"),
    ("draft_memo", "Draft memo"),
    ("verify_numbers", "Verify numbers"),
    ("human_review", "Advisor review"),
]
MAX_REDRAFTS = 2


class State(TypedDict, total=False):
    case_id: str
    run_id: str
    redrafts: int
    unverified: list[str]
    review_note: str | None
    new_version: bool


def checkpointer_url() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def ensure_checkpointer() -> None:
    """Create LangGraph's checkpoint tables once per process. Its migrations build indexes
    CONCURRENTLY, which waits for open transactions, so never call this inside a request."""
    with PostgresSaver.from_conn_string(checkpointer_url()) as saver:
        saver.setup()


# ---------------------------------------------------------------- progress bookkeeping


def _now() -> str:
    return datetime.now(UTC).isoformat()


def set_step(run_id: str, name: str, status: str, note: str | None = None) -> None:
    with SessionLocal() as db:
        run = db.get_one(PrepareRun, uuid.UUID(run_id))
        steps = [dict(s) for s in run.steps]
        for step in steps:
            if step["name"] == name:
                step["status"] = status
                if status == "running":
                    step["started_at"], step["finished_at"] = _now(), None
                if status in ("done", "failed"):
                    step["finished_at"] = _now()
                if note is not None:
                    step["note"] = note
        run.steps = steps
        db.commit()


def node(name: str) -> Callable:
    """Wrap a node: mark its step running/done/failed and trace it."""

    def decorate(fn: Callable[[Session, Case, State], Any]) -> Callable[[State], Any]:
        @wraps(fn)
        def run(state: State) -> Any:
            set_step(state["run_id"], name, "running")
            try:
                with span(f"agent.{name}", case_id=state["case_id"]), SessionLocal() as db:
                    case = db.get_one(Case, uuid.UUID(state["case_id"]))
                    result = fn(db, case, state)
                    db.commit()
            except Exception:
                set_step(state["run_id"], name, "failed")
                raise
            note = result.pop("_note", None) if isinstance(result, dict) else None
            set_step(state["run_id"], name, "done", note)
            return result

        return run

    return decorate


# ---------------------------------------------------------------- nodes


def latest_memo(db: Session, case_id: uuid.UUID) -> Memo | None:
    query = select(Memo).where(Memo.case_id == case_id).order_by(Memo.version.desc()).limit(1)
    return db.scalars(query).first()


@node("check_documents")
def check_documents(db: Session, case: Case, state: State) -> dict:
    """Missing documents are recorded; the run continues anyway."""
    years = [y for y in db.scalars(select(Document.year).where(
        Document.case_id == case.id, Document.kind == "annual_report",
        Document.status == "indexed")) if y]  # fmt: skip
    transactions = list(db.scalars(select(Transaction).where(Transaction.case_id == case.id)))
    items = missing_documents(case.applied_on, years, compute_cashflow(transactions))
    missing = [i["document"] for i in items if not i["present"]]
    case.status = "analysing"
    return {"_note": f"Missing: {', '.join(missing)}" if missing else "All base documents present"}


@node("analyse")
def analyse(db: Session, case: Case, state: State) -> dict:
    analysis = run_analysis(db, case.id)
    errors = analysis.ratios.get("errors", [])
    flags = len(analysis.red_flags)
    note = f"{flags} red flag{'s' * (flags != 1)}" + (f", {len(errors)} extraction errors"
                                                     if errors else "")  # fmt: skip
    return {"_note": note}


@node("find_similar")
def find_similar(db: Session, case: Case, state: State) -> dict:
    analysis = db.get_one(Analysis, case.id)
    analysis.similar = similar_cases(db, case)
    return {"_note": f"{len(analysis.similar)} precedents"}


@node("match_lenders")
def match(db: Session, case: Case, state: State) -> dict:
    analysis = db.get_one(Analysis, case.id)
    result = match_lenders(db, case)
    analysis.lender_matches = result
    fits = sum(1 for lender in result["lenders"] if lender["passes_hard_checks"])
    return {"_note": f"{fits} of {len(result['lenders'])} pass the hard checks"}


@node("draft_memo")
def draft_memo(db: Session, case: Case, state: State) -> dict:
    analysis = db.get_one(Analysis, case.id)
    sources = memos.gather_evidence(db, case, analysis.similar or [], analysis.lender_matches)
    text = memos.draft(db, case, sources, state.get("unverified", []), state.get("review_note"))
    latest = latest_memo(db, case.id)
    if latest is None or state.get("new_version", True):
        version = (latest.version if latest else 0) + 1
        latest = Memo(case_id=case.id, version=version, content_md=text, review_note=None)
        db.add(latest)
    latest.content_md = text
    latest.sources = memos.source_refs(sources)
    latest.status = "draft"
    redraft = not state.get("new_version", True)
    return {"new_version": False, "redrafts": state.get("redrafts", 0) + int(redraft),
            "_note": f"Version {latest.version}" + (" (redraft)" if redraft else "")}  # fmt: skip


@node("verify_numbers")
def verify(db: Session, case: Case, state: State) -> dict:
    latest = latest_memo(db, case.id)
    assert latest is not None
    sources = [memos.Source(**s) for s in latest.sources]
    result = memos.verify_numbers(latest.content_md, sources)
    history = list((latest.verification or {}).get("attempts", []))
    history.append({"unverified": result["unverified"], "total": result["total"]})
    missing = memos.missing_sections(latest.content_md)
    latest.verification = {**result, "attempts": history, "missing_sections": missing}
    note = f"{result['verified']} of {result['total']} numbers verified"
    return {"unverified": result["unverified"], "_note": note}


def after_verify(state: State) -> str:
    if state.get("unverified") and state.get("redrafts", 0) < MAX_REDRAFTS:
        return "draft_memo"
    return "human_review"


def human_review(state: State) -> Command:
    """Pause until the advisor approves or requests changes (LangGraph interrupt)."""
    with SessionLocal() as db:
        run = db.get_one(PrepareRun, uuid.UUID(state["run_id"]))
        case = db.get_one(Case, uuid.UUID(state["case_id"]))
        run.status, case.status = "waiting_review", "waiting_review"
        db.commit()
    set_step(state["run_id"], "human_review", "waiting", "Waiting for the advisor")
    decision = interrupt({"case_id": state["case_id"]})  # resumes here with the decision
    with SessionLocal() as db:
        latest = latest_memo(db, uuid.UUID(state["case_id"]))
        assert latest is not None
        run = db.get_one(PrepareRun, uuid.UUID(state["run_id"]))
        case = db.get_one(Case, uuid.UUID(state["case_id"]))
        run.status = "running"
        if decision["action"] == "approve":
            latest.status, latest.approved_at = "approved", datetime.now(UTC)
            latest.approved_by = uuid.UUID(decision["user_id"])
            case.status = "ready"
            db.commit()
            set_step(state["run_id"], "human_review", "done", f"Approved version {latest.version}")
            return Command(goto="finalise")
        latest.status, latest.review_note = "changes_requested", decision["note"]
        case.status = "analysing"
        db.commit()
    set_step(state["run_id"], "human_review", "pending", "Changes requested")
    update = {"review_note": decision["note"], "new_version": True, "redrafts": 0,
              "unverified": []}  # fmt: skip
    return Command(goto="draft_memo", update=update)


def finalise(state: State) -> dict:
    with SessionLocal() as db:
        db.get_one(PrepareRun, uuid.UUID(state["run_id"])).status = "done"
        db.commit()
    return {}


def build_graph() -> StateGraph:
    graph = StateGraph(State)
    graph.add_node("check_documents", check_documents)
    graph.add_node("analyse", analyse)
    graph.add_node("find_similar", find_similar)
    graph.add_node("match_lenders", match)
    graph.add_node("draft_memo", draft_memo)
    graph.add_node("verify_numbers", verify)
    graph.add_node("human_review", human_review, destinations=("draft_memo", "finalise"))
    graph.add_node("finalise", finalise)
    graph.add_edge(START, "check_documents")
    graph.add_edge("check_documents", "analyse")
    graph.add_edge("analyse", "find_similar")
    graph.add_edge("find_similar", "match_lenders")
    graph.add_edge("match_lenders", "draft_memo")
    graph.add_edge("draft_memo", "verify_numbers")
    graph.add_conditional_edges("verify_numbers", after_verify, ["draft_memo", "human_review"])
    graph.add_edge("finalise", END)
    return graph


# ---------------------------------------------------------------- running


def thread_id(run: PrepareRun) -> str:
    return f"{run.case_id}:{run.run_number}"


def new_run(db: Session, case: Case) -> PrepareRun:
    number = (db.scalar(select(func.max(PrepareRun.run_number))
                        .where(PrepareRun.case_id == case.id)) or 0) + 1  # fmt: skip
    run = PrepareRun(case_id=case.id, run_number=number, status="running",
                     steps=[{"name": n, "label": label, "status": "pending", "started_at": None,
                             "finished_at": None, "note": None} for n, label in STEPS])  # fmt: skip
    db.add(run)
    db.commit()
    return run


def execute(run_id: uuid.UUID, resume: dict | None = None) -> None:
    """Start a run (resume=None) or resume one after advisor review. Runs in the background."""
    with SessionLocal() as db:
        run = db.get_one(PrepareRun, run_id)
        config = {"configurable": {"thread_id": thread_id(run)}}
        payload: Any = Command(resume=resume) if resume is not None else {
            "case_id": str(run.case_id), "run_id": str(run.id), "redrafts": 0,
            "new_version": True, "unverified": [], "review_note": None}  # fmt: skip
    try:
        ensure_checkpointer()
        with PostgresSaver.from_conn_string(checkpointer_url()) as saver:
            build_graph().compile(checkpointer=saver).invoke(payload, config)
    except Exception as exc:
        log.exception("Prepare run %s failed", run_id)
        with SessionLocal() as db:
            run = db.get_one(PrepareRun, run_id)
            run.status, run.error = "failed", str(exc)[:500]
            db.commit()


def delete_checkpoints(db: Session, case_id: uuid.UUID) -> None:
    """Right to erasure: remove the agent's checkpoints for every run of a case."""
    with PostgresSaver.from_conn_string(checkpointer_url()) as saver:
        for number in db.scalars(
            select(PrepareRun.run_number).where(PrepareRun.case_id == case_id)
        ):
            saver.delete_thread(f"{case_id}:{number}")
