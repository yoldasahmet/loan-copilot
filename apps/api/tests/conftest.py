"""Test setup: a separate database (<name>_test), migrated once, truncated after every test."""

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

_base = make_url(
    os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://loancopilot:loancopilot@localhost:5433/loancopilot"
)
TEST_DB = f"{_base.database}_test"
os.environ["DATABASE_URL"] = _base.set(database=TEST_DB).render_as_string(hide_password=False)
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="loancopilot-test-")
os.environ["EMBEDDINGS_BACKEND"] = "fake"
os.environ["RERANK"] = "off"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["ANTHROPIC_API_KEY"] = ""


def _create_database() -> None:
    admin = _base.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


_create_database()

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from loancopilot.auth import hash_password  # noqa: E402
from loancopilot.db import SessionLocal, engine  # noqa: E402
from loancopilot.main import app  # noqa: E402
from loancopilot.models import Base, User  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def login() -> Callable[..., TestClient]:
    """Create a user with the given role and return a TestClient logged in as them."""

    def _login(role: str = "advisor", email: str | None = None) -> TestClient:
        email = email or f"{role}-{os.urandom(4).hex()}@example.com"
        with SessionLocal() as db:
            db.add(User(email=email, name=email.split("@")[0], role=role,
                        password_hash=hash_password(PASSWORD)))  # fmt: skip
            db.commit()
        c = TestClient(app, base_url="http://localhost")
        assert c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success
        return c

    return _login


FAKE_PDF_BLOCKS = [
    ("header", "Testbouw B.V.", 1),
    ("text", "Annual report 2025", 1),
    ("header", "Directors' report", 2),
    ("text", " ".join(["Revenue rose because of heat-pump projects."] * 40), 2),
    ("header", "Balance sheet as at 31 December 2025", 3),
    ("header", "Amounts in EUR", 3),
    ("table", "| | 2025 |\n|---|---|\n| Total assets | 2,000,000 |", 3),
]


@pytest.fixture(autouse=True)
def fake_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docling needs large layout models; API tests use a fixed parse result instead.

    The chunker itself is tested directly in test_chunking.py.
    """
    from loancopilot import ingest
    from loancopilot.ingest_pdf import Block, ParsedPdf

    def parse(_path: Path) -> ParsedPdf:
        return ParsedPdf([Block(k, t, p) for k, t, p in FAKE_PDF_BLOCKS], page_count=3)

    monkeypatch.setattr(ingest, "parse_pdf", parse)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    from loancopilot import llm
    from tests.fake_llm import FakeLlm

    fake = FakeLlm()
    monkeypatch.setattr(llm, "_call", fake.call)
    monkeypatch.setattr(llm, "_stream_call", fake.stream_call)
    return fake
