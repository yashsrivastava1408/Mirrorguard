"""Saving, masking and purging guardrail events in a real database."""

import json
from datetime import UTC, datetime, timedelta

from mirrorguard.db import Database
from mirrorguard.guardrail.stores.event_store import NOT_STORED, EventRepository
from mirrorguard.privacy.redaction import PatternRedactor
from tests.support.fakes import make_event


async def test_events_are_saved_and_read_back_per_tenant_and_session(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    await database.create_tables()
    events = EventRepository(database)
    await events.save(make_event(signals=("no sleep",), issues=("x",), original_reply="old"))
    await events.save(make_event(tenant_id="other"))
    rows = await events.for_session("t", "s")
    assert len(rows) == 1
    assert (rows[0].signals, rows[0].issues, rows[0].original_reply) == (["no sleep"], ["x"], "old")
    assert json.dumps(rows[0].signals)
    await database.dispose()


async def test_events_are_masked_before_they_are_stored(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'e.db'}")
    await database.create_tables()
    events = EventRepository(database, redactor=PatternRedactor())
    await events.save(
        make_event(user_message="I am at a@b.com", reply="ok a@b.com", original_reply="was a@b.com")
    )
    await events.save(make_event(session_id="private", user_message="secret", store_text=False))
    row = (await events.for_session("t", "s"))[0]
    assert (row.user_message, row.reply, row.original_reply) == (
        "I am at [EMAIL]", "ok [EMAIL]", "was [EMAIL]",
    )  # fmt: skip
    private = (await events.for_session("t", "private"))[0]
    assert (private.user_message, private.reply) == (NOT_STORED, NOT_STORED)
    assert private.original_reply is None and private.risk_level == "medium"
    await database.dispose()


async def test_old_events_are_purged_with_their_reviews(tmp_path):
    from sqlalchemy import func, select, update

    from mirrorguard.db.models import GuardrailEventRecord, ReviewRecord

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")
    await database.create_tables()
    events = EventRepository(database)
    for session_id in ("old", "new"):
        await events.save(make_event(session_id=session_id))
    old = (await events.for_session("t", "old"))[0]
    await events.add_review("t", old.id, verdict="correct", note="", reviewer="")
    async with database.session() as session, session.begin():
        await session.execute(
            update(GuardrailEventRecord)
            .where(GuardrailEventRecord.id == old.id)
            .values(created_at=datetime.now(UTC) - timedelta(days=100))
        )
    assert await events.purge_older_than(datetime.now(UTC) - timedelta(days=90)) == 1
    assert await events.for_session("t", "old") == []
    assert len(await events.for_session("t", "new")) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ReviewRecord)) == 0
    await database.dispose()
