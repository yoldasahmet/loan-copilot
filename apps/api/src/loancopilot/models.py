"""SQLAlchemy models for every table in the data model (spec §6)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 1024
Money = Numeric(14, 2)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB, Decimal: Money}


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def _fk(target: str, *, nullable: bool = False, cascade: bool = True) -> Mapped[Any]:
    ondelete = "CASCADE" if cascade else "SET NULL"
    return mapped_column(ForeignKey(target, ondelete=ondelete), index=True, nullable=nullable)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # admin | advisor
    created_at: Mapped[datetime] = _created()


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str | None] = mapped_column(String(300))  # null for historical cases
    kvk_number: Mapped[str | None] = mapped_column(String(8))
    legal_form: Mapped[str] = mapped_column(String(20))  # bv | eenmanszaak | vof | other
    sbi_code: Mapped[str | None] = mapped_column(String(10))
    sector_group: Mapped[str | None] = mapped_column(String(40))
    founded_year: Mapped[int | None]
    employees: Mapped[int | None]
    city: Mapped[str | None] = mapped_column(String(100))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = _id()
    company_id: Mapped[uuid.UUID] = _fk("companies.id")
    advisor_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, cascade=False)
    status: Mapped[str] = mapped_column(String(20), default="intake")
    loan_amount: Mapped[Decimal]
    loan_purpose: Mapped[str] = mapped_column(String(20))
    loan_term_months: Mapped[int]
    notes: Mapped[str | None] = mapped_column(Text)
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    historical_ref: Mapped[str | None] = mapped_column(String(10), unique=True)  # H-0042
    applied_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Lender(Base):
    __tablename__ = "lenders"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200), unique=True)
    product_type: Mapped[str] = mapped_column(String(40))
    min_amount: Mapped[Decimal]
    max_amount: Mapped[Decimal]
    min_revenue: Mapped[Decimal]
    min_years_trading: Mapped[int]
    excluded_sector_groups: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    allowed_legal_forms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    typical_rate_min: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    typical_rate_max: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID | None] = _fk("cases.id", nullable=True)
    lender_id: Mapped[uuid.UUID | None] = _fk("lenders.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    year: Mapped[int | None]
    page_count: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text)
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    injection_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (UniqueConstraint("case_id", "sha256"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = _id()
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    case_id: Mapped[uuid.UUID | None] = _fk("cases.id", nullable=True)
    lender_id: Mapped[uuid.UUID | None] = _fk("lenders.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # text | table | analysis
    section: Mapped[str | None] = mapped_column(String(300))
    page_from: Mapped[int | None]
    page_to: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)
    context_header: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(context_header, '') || ' ' || text)", persisted=True
        ),  # fmt: skip
    )
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),  # fmt: skip
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    document_id: Mapped[uuid.UUID] = _fk("documents.id")
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal]
    counterparty_name: Mapped[str | None] = mapped_column(String(300))
    counterparty_iban: Mapped[str | None] = mapped_column(String(34))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="other")
    balance_after: Mapped[Decimal | None]


class Financial(Base):
    __tablename__ = "financials"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    year: Mapped[int]
    revenue: Mapped[Decimal | None]
    cost_of_sales: Mapped[Decimal | None]
    gross_profit: Mapped[Decimal | None]
    operating_expenses: Mapped[Decimal | None]
    ebitda: Mapped[Decimal | None]
    depreciation: Mapped[Decimal | None]
    interest_expense: Mapped[Decimal | None]
    net_income: Mapped[Decimal | None]
    total_assets: Mapped[Decimal | None]
    current_assets: Mapped[Decimal | None]
    cash: Mapped[Decimal | None]
    equity: Mapped[Decimal | None]
    current_liabilities: Mapped[Decimal | None]
    long_term_debt: Mapped[Decimal | None]
    sources: Mapped[dict[str, Any]] = mapped_column(default=dict)
    warnings: Mapped[list[Any]] = mapped_column(default=list)
    edited_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, cascade=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (UniqueConstraint("case_id", "year"),)


class Analysis(Base):
    __tablename__ = "analyses"
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    ratios: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cashflow: Mapped[dict[str, Any]] = mapped_column(default=dict)
    red_flags: Mapped[list[Any]] = mapped_column(default=list)
    missing_documents: Mapped[list[Any]] = mapped_column(default=list)
    computed_at: Mapped[datetime] = _created()


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    lender_id: Mapped[uuid.UUID] = _fk("lenders.id")
    decision: Mapped[str] = mapped_column(String(20))  # approved | declined | withdrawn
    amount_granted: Mapped[Decimal | None]
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    term_months: Mapped[int | None]
    decline_reason: Mapped[str | None] = mapped_column(Text)
    documents_requested: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    decided_on: Mapped[date] = mapped_column(Date)


class CaseCard(Base):
    __tablename__ = "case_cards"
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    profile_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', profile_text)", persisted=True)
    )
    sector_group: Mapped[str | None] = mapped_column(String(40), index=True)
    revenue_band: Mapped[str | None] = mapped_column(String(10))
    loan_purpose: Mapped[str | None] = mapped_column(String(20))
    first_decided_on: Mapped[date | None] = mapped_column(Date, index=True)

    __table_args__ = (
        Index(
            "ix_case_cards_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),  # fmt: skip
        Index("ix_case_cards_tsv", "tsv", postgresql_using="gin"),
    )


class PrepareRun(Base):
    __tablename__ = "prepare_runs"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    run_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="running")
    steps: Mapped[list[Any]] = mapped_column(default=list)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Memo(Base):
    __tablename__ = "memos"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    version: Mapped[int]
    content_md: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    verification: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    review_note: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, cascade=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    __table_args__ = (UniqueConstraint("case_id", "version"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[uuid.UUID] = _id()
    case_id: Mapped[uuid.UUID] = _fk("cases.id")
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, cascade=False)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created()


class AiRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[uuid.UUID] = _id()
    # SET NULL keeps the audit row (metadata) when a case is erased.
    case_id: Mapped[uuid.UUID | None] = _fk("cases.id", nullable=True, cascade=False)
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, cascade=False)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    source_ids: Mapped[list[Any]] = mapped_column(default=list)
    output_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
