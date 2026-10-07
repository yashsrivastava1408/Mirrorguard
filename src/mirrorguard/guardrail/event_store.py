"""Saves and loads guardrail events."""

from datetime import datetime

from sqlalchemy import Integer, cast, func, select

from mirrorguard.db import Database
from mirrorguard.db.models import GuardrailEventRecord, ReviewRecord
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

    async def get(self, tenant_id: str, event_id: str) -> GuardrailEventRecord | None:
        async with self._db.session() as session:
            record = await session.get(GuardrailEventRecord, event_id)
            return record if record and record.tenant_id == tenant_id else None

    async def list(
        self,
        tenant_id: str,
        *,
        risk_level: str | None = None,
        unreviewed_only: bool = False,
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[tuple[GuardrailEventRecord, ReviewRecord | None]]:
        """Newest first. Pass the last row's time as `before` to get the next page."""
        query = (
            select(GuardrailEventRecord, ReviewRecord)
            .outerjoin(ReviewRecord, ReviewRecord.event_id == GuardrailEventRecord.id)
            .where(GuardrailEventRecord.tenant_id == tenant_id)
            .order_by(GuardrailEventRecord.created_at.desc())
            .limit(limit)
        )
        if risk_level:
            query = query.where(GuardrailEventRecord.session_level == risk_level)
        if unreviewed_only:
            query = query.where(
                GuardrailEventRecord.session_level != "low", ReviewRecord.id.is_(None)
            )
        if before:
            query = query.where(GuardrailEventRecord.created_at < before)
        async with self._db.session() as session:
            return [(event, review) for event, review in await session.execute(query)]

    async def add_review(
        self, tenant_id: str, event_id: str, *, verdict: str, note: str, reviewer: str
    ) -> bool:
        """Save or replace the verdict on an event. False when the event is not this tenant's."""
        async with self._db.session() as session, session.begin():
            event = await session.get(GuardrailEventRecord, event_id)
            if event is None or event.tenant_id != tenant_id:
                return False
            review = await session.scalar(
                select(ReviewRecord).where(ReviewRecord.event_id == event_id)
            )
            if review is None:
                review = ReviewRecord(event_id=event_id, tenant_id=tenant_id)
                session.add(review)
            review.verdict, review.note, review.reviewer = verdict, note, reviewer
            return True

    async def stats(self, tenant_id: str, since: datetime) -> dict:
        """Counts for the dashboard, worked out by the database."""
        events = GuardrailEventRecord
        scope = (events.tenant_id == tenant_id, events.created_at >= since)
        if self._db.engine.dialect.name == "sqlite":
            hour = func.strftime("%Y-%m-%dT%H:00", events.created_at)
        else:
            hour = func.to_char(func.date_trunc("hour", events.created_at), 'YYYY-MM-DD"T"HH24:00')

        def as_int(column):
            return func.coalesce(func.sum(cast(column, Integer)), 0)

        async with self._db.session() as session:
            by_level = await session.execute(
                select(events.session_level, func.count())
                .where(*scope)
                .group_by(events.session_level)
            )
            by_action = await session.execute(
                select(events.action, func.count()).where(*scope).group_by(events.action)
            )
            totals = (
                await session.execute(
                    select(
                        func.count(),
                        func.count(func.distinct(events.session_id)),
                        as_int(events.rewritten),
                        as_int(events.crisis),
                        as_int(events.from_fallback),
                    ).where(*scope)
                )
            ).one()
            timeline = await session.execute(
                select(hour, events.session_level, func.count())
                .where(*scope)
                .group_by(hour, events.session_level)
                .order_by(hour)
            )
            reviews = await session.execute(
                select(ReviewRecord.verdict, func.count())
                .join(events, events.id == ReviewRecord.event_id)
                .where(*scope)
                .group_by(ReviewRecord.verdict)
            )
            hours: dict[str, dict[str, int]] = {}
            for bucket, level, count in timeline:
                hours.setdefault(bucket, {"low": 0, "medium": 0, "high": 0})[level] = count
            return {
                "turns": totals[0],
                "sessions": totals[1],
                "rewritten": totals[2],
                "crisis": totals[3],
                "scorer_fallbacks": totals[4],
                "by_level": {"low": 0, "medium": 0, "high": 0} | dict(by_level.all()),
                "by_action": {"pass": 0, "steer": 0, "check": 0} | dict(by_action.all()),
                "reviews": dict(reviews.all()),
                "timeline": [{"hour": bucket, **counts} for bucket, counts in hours.items()],
            }
