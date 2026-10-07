"""Database tables."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConversationRecord(Base):
    """One benchmark job: a scenario played against one target model."""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("run_id", "job_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("benchmark_runs.id"), index=True)
    job_key: Mapped[str] = mapped_column(String(300))
    scenario_id: Mapped[str] = mapped_column(String(100), index=True)
    persona_id: Mapped[str] = mapped_column(String(100), index=True)
    target_model: Mapped[str] = mapped_column(String(200), index=True)
    guardrail: Mapped[bool] = mapped_column(default=False)
    repeat: Mapped[int] = mapped_column(default=0)
    # pending -> conversed (transcript saved) -> done (scored); or failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    transcript: Mapped[list | None] = mapped_column(JSON, default=None)
    guardrail_trace: Mapped[list | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ScoreRecord(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), unique=True)
    judge_model: Mapped[str] = mapped_column(String(200))
    rubric_version: Mapped[str] = mapped_column(String(20))
    measure_scores: Mapped[dict] = mapped_column(JSON)
    turn_scores: Mapped[list] = mapped_column(JSON)
    total: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GuardrailEventRecord(Base):
    """One guarded chat turn."""

    __tablename__ = "guardrail_events"
    __table_args__ = (
        Index("ix_events_tenant_time", "tenant_id", "created_at"),
        Index("ix_events_tenant_session", "tenant_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(200))
    user_message: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    original_reply: Mapped[str | None] = mapped_column(Text, default=None)
    risk_level: Mapped[str] = mapped_column(String(10), index=True)
    session_level: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(10))
    shadow: Mapped[bool] = mapped_column(default=False)
    crisis: Mapped[bool] = mapped_column(default=False)
    rewritten: Mapped[bool] = mapped_column(default=False)
    from_fallback: Mapped[bool] = mapped_column(default=False)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PolicyRecord(Base):
    """A tenant's guardrail policy. Tenants without a row use the default policy."""

    __tablename__ = "policies"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ReviewRecord(Base):
    """A human reviewer's verdict on one guardrail event."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("guardrail_events.id"), unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TenantRecord(Base):
    """One customer organisation."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiKeyRecord(Base):
    """An API key. Only its hash is stored, so a database leak does not leak keys."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AuditRecord(Base):
    """Who changed what. Rows are only ever added, never changed or deleted."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
