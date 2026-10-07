"""The background event queue."""

import asyncio

from mirrorguard.guardrail.events import QueueSink
from tests.support.fakes import make_event


async def test_queue_sink_writes_in_the_background():
    written = []

    async def write(item):
        written.append(item)

    sink = QueueSink(write)
    sink.start()
    await sink.emit(make_event())
    await sink.emit(make_event(session_id="s2"))
    await sink.flush()
    assert [e.session_id for e in written] == ["s", "s2"]
    await sink.stop()


async def test_queue_sink_drops_events_when_full_instead_of_blocking():
    sink = QueueSink(lambda item: asyncio.sleep(0), max_queue=1)
    await sink.emit(make_event())
    await sink.emit(make_event())
    assert sink.dropped == 1


async def test_queue_sink_survives_a_failing_writer_and_drains_on_stop():
    written = []

    async def write(item):
        if item.session_id == "bad":
            raise RuntimeError("database is down")
        written.append(item.session_id)

    sink = QueueSink(write)
    sink.start()
    for name in ("bad", "good"):
        await sink.emit(make_event(session_id=name))
    await sink.stop()
    assert written == ["good"]
