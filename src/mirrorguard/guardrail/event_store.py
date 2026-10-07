"""Saves and loads guardrail events."""

from sqlalchemy import select

from mirrorguard.db import Database
from mirrorguard.db.models import GuardrailEventRecord
from mirrorguard.guardrail.types import GuardrailEvent


class EventRepository:
    def __init__(self, database: Database):
        self._db = database

    async def save(self, event: GuardrailEvent) -> None:
        async with self._db.session() as session, session.begin():
            session.add(
                GuardrailEventRecord(
                    tenant_id=event.tenant_id,
                    session_id=event.session_id,
                    model=event.model,
                    user_message=event.user_message,
                    reply=event.reply,
                    original_reply=event.original_reply,
                    risk_level=event.risk_level,
                    session_level=event.session_level,
                    action=event.action,
                    shadow=event.shadow,
                    crisis=event.crisis,
                    rewritten=event.rewritten,
                    from_fallback=event.from_fallback,
                    signals=list(event.signals),
                    issues=list(event.issues),
                )
            )

    async def for_session(
        self, tenant_id: str, session_id: str, *, limit: int = 200
    ) -> list[GuardrailEventRecord]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(GuardrailEventRecord)
                .where(
                    GuardrailEventRecord.tenant_id == tenant_id,
                    GuardrailEventRecord.session_id == session_id,
                )
                .order_by(GuardrailEventRecord.created_at)
                .limit(limit)
            )
            return list(rows)
