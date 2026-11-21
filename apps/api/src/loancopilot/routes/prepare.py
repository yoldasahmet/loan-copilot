"""Prepare application (agent run), memo versions and advisor review."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from loancopilot import agent
from loancopilot.auth import DB, CurrentUser, get_case
from loancopilot.models import Memo, PrepareRun, User

router = APIRouter(tags=["prepare"])


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_number: int
    status: str
    steps: list[dict[str, Any]]
    error: str | None
    created_at: datetime
    updated_at: datetime


class MemoOut(BaseModel):
    id: uuid.UUID
    version: int
    content_md: str
    sources: list[dict[str, Any]]
    verification: dict[str, Any]
    status: str
    review_note: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    versions: list[dict[str, Any]]


class ChangesIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


def _latest_run(db: DB, case_id: uuid.UUID) -> PrepareRun | None:
    query = (select(PrepareRun).where(PrepareRun.case_id == case_id)
             .order_by(PrepareRun.run_number.desc()).limit(1))  # fmt: skip
    return db.scalars(query).first()


@router.post("/cases/{case_id}/prepare", status_code=202)
def start_prepare(case_id: uuid.UUID, db: DB, user: CurrentUser,
                  background: BackgroundTasks) -> RunOut:  # fmt: skip
    case = get_case(db, user, case_id)
    if case.advisor_id is None:
        raise HTTPException(422, "Assign an advisor to the case first.")
    latest = _latest_run(db, case.id)
    if latest is not None and latest.status == "running":
        raise HTTPException(409, "A run is already in progress.")
    if latest is not None and latest.status == "waiting_review":
        latest.status = "done"  # superseded by a fresh run
        db.commit()
    run = agent.new_run(db, case)
    background.add_task(agent.execute, run.id)
    return RunOut.model_validate(run)


@router.get("/cases/{case_id}/prepare")
def read_prepare(case_id: uuid.UUID, db: DB, user: CurrentUser) -> RunOut | None:
    run = _latest_run(db, get_case(db, user, case_id).id)
    return RunOut.model_validate(run) if run else None


def _waiting_run(db: DB, case_id: uuid.UUID) -> PrepareRun:
    run = _latest_run(db, case_id)
    if run is None or run.status != "waiting_review":
        raise HTTPException(409, "There is no memo waiting for review.")
    return run


@router.post("/cases/{case_id}/memo/approve", status_code=202)
def approve_memo(case_id: uuid.UUID, db: DB, user: CurrentUser,
                 background: BackgroundTasks) -> RunOut:  # fmt: skip
    run = _waiting_run(db, get_case(db, user, case_id).id)
    run.status = "running"
    db.commit()
    background.add_task(agent.execute, run.id, {"action": "approve", "user_id": str(user.id)})
    return RunOut.model_validate(run)


@router.post("/cases/{case_id}/memo/request-changes", status_code=202)
def request_changes(case_id: uuid.UUID, body: ChangesIn, db: DB, user: CurrentUser,
                    background: BackgroundTasks) -> RunOut:  # fmt: skip
    run = _waiting_run(db, get_case(db, user, case_id).id)
    run.status = "running"
    db.commit()
    resume = {"action": "request_changes", "note": body.note, "user_id": str(user.id)}
    background.add_task(agent.execute, run.id, resume)
    return RunOut.model_validate(run)


@router.get("/cases/{case_id}/memo")
def read_memo(case_id: uuid.UUID, db: DB, user: CurrentUser,
              version: int | None = None) -> MemoOut | None:  # fmt: skip
    case = get_case(db, user, case_id)
    memos = list(db.scalars(select(Memo).where(Memo.case_id == case.id).order_by(Memo.version)))
    if not memos:
        return None
    memo = next((m for m in memos if m.version == version), None) if version else memos[-1]
    if memo is None:
        raise HTTPException(404, "Memo version not found")
    approver = db.get(User, memo.approved_by) if memo.approved_by else None
    versions = [{"version": m.version, "status": m.status, "created_at": m.created_at}
                for m in memos]  # fmt: skip
    return MemoOut(
        id=memo.id, version=memo.version, content_md=memo.content_md, sources=memo.sources,
        verification=memo.verification, status=memo.status, review_note=memo.review_note,
        approved_by=approver.name if approver else None, approved_at=memo.approved_at,
        created_at=memo.created_at, versions=versions,
    )  # fmt: skip
