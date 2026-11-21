import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from loancopilot.auth import DB, AdminUser, hash_password
from loancopilot.models import User
from loancopilot.schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])

Role = Literal["admin", "advisor"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    role: Role = "advisor"
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


@router.get("/users")
def list_users(db: DB, admin: AdminUser) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in db.scalars(select(User).order_by(User.name))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: DB, admin: AdminUser) -> UserOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with this email already exists")
    user = User(name=body.name, email=email, role=body.role,
                password_hash=hash_password(body.password))  # fmt: skip
    db.add(user)
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DB, admin: AdminUser) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.role and user.id == admin.id and body.role != "admin":
        raise HTTPException(422, "You cannot remove your own admin role")
    if body.name:
        user.name = body.name
    if body.role:
        user.role = body.role
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    return UserOut.model_validate(user)
