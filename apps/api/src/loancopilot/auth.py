"""Password hashing, signed session cookies, current user and the case access filter."""

import uuid
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from loancopilot.config import get_settings
from loancopilot.db import get_db
from loancopilot.models import Case, User

COOKIE = "lc_session"
MAX_AGE_SECONDS = 8 * 60 * 60
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

_hasher = PasswordHasher()

DB = Annotated[Session, Depends(get_db)]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="session")


def set_session(request: Request, response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE,
        _serializer().dumps(str(user.id)),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.hostname not in LOCAL_HOSTS,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request, db: DB) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not logged in")
    try:
        user_id = uuid.UUID(_serializer().loads(token, max_age=MAX_AGE_SECONDS))
    except (BadSignature, ValueError) as exc:
        raise HTTPException(401, "Session expired") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Not logged in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def allowed_case_ids(user: User) -> Select[tuple[uuid.UUID]]:
    """SQL subquery of the open cases this user may see. Use inside WHERE, never filter after."""
    query = select(Case.id).where(Case.is_historical.is_(False))
    if user.role != "admin":
        query = query.where(Case.advisor_id == user.id)
    return query


def get_case(db: Session, user: User, case_id: uuid.UUID) -> Case:
    """Load a case the user can access, or 404 (never 403, so existence is not revealed)."""
    case = db.scalar(select(Case).where(Case.id == case_id, Case.id.in_(allowed_case_ids(user))))
    if case is None:
        raise HTTPException(404, "Case not found")
    return case
