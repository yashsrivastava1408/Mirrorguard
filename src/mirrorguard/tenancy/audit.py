"""The audit log: a record of who changed what. It can be added to and read, nothing else."""

from sqlalchemy import select

from mirrorguard.db import Database
from mirrorguard.db.models import AuditRecord


class AuditLog:
    def __init__(self, database: Database):
        self._db = database

    async def record(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        *,
        target: str = "",
        detail: dict | None = None,
    ) -> None:
        async with self._db.session() as session, session.begin():
            session.add(
                AuditRecord(
                    tenant_id=tenant_id,
                    actor=actor,
                    action=action,
                    target=target,
                    detail=detail or {},
                )
            )

    async def list(self, tenant_id: str, *, limit: int = 100) -> list[AuditRecord]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(AuditRecord)
                .where(AuditRecord.tenant_id == tenant_id)
                .order_by(AuditRecord.created_at.desc())
                .limit(limit)
            )
            return list(rows)
