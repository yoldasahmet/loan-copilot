from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from loancopilot.auth import (
    DB,
    CurrentUser,
    clear_session,
    hash_password,
    set_session,
    verify_password,
)
from loancopilot.models import User
from loancopilot.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class SetupStatus(BaseModel):
    needed: bool


def _setup_needed(db: DB) -> bool:
    return db.scalar(select(func.count()).select_from(User)) == 0


@router.get("/setup")
def setup_status(db: DB) -> SetupStatus:
    return SetupStatus(needed=_setup_needed(db))


@router.post("/setup")
def setup(body: SetupIn, request: Request, response: Response, db: DB) -> UserOut:
    if not _setup_needed(db):
        raise HTTPException(404, "Not found")
    user = User(name=body.name, email=body.email.lower(), role="admin",
                password_hash=hash_password(body.password))  # fmt: skip
    db.add(user)
    db.commit()
    set_session(request, response, user)
    return UserOut.model_validate(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB) -> UserOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Wrong email or password")
    set_session(request, response, user)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    clear_session(response)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
