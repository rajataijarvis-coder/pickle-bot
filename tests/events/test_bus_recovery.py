# tests/events/test_bus_recovery.py
import json
import pytest
import asyncio
import tempfile
from pathlib import Path
from picklebot.events.bus import EventBus
from picklebot.events.types import Event, EventType


@pytest.fixture
def temp_events_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_recover_republishes_pending_events(temp_events_dir):
    # Create a pending event file manually
    pending_dir = temp_events_dir / "pending"
    pending_dir.mkdir(parents=True)

    event_data = {
        "type": "outbound",
        "session_id": "test-session",
        "content": "Hello",
        "source": "agent:pickle",
        "timestamp": 12345.0,
        "metadata": {},
    }

    with open(pending_dir / "12345.0_test-session.json", "w") as f:
        json.dump(event_data, f)

    # Create bus and track received events
    received = []

    async def handler(event: Event):
        received.append(event)

    bus = EventBus(events_dir=temp_events_dir)
    bus.subscribe(EventType.OUTBOUND, handler)

    # Start EventBus worker (which runs recovery on startup)
    eventbus_task = bus.start()

    try:
        # Allow recovery to complete
        await asyncio.sleep(0.1)

        # Event should have been recovered and dispatched
        assert len(received) == 1
        assert received[0].session_id == "test-session"
    finally:
        eventbus_task.cancel()
        try:
            await eventbus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_recover_empty_pending_dir(temp_events_dir):
    bus = EventBus(events_dir=temp_events_dir)

    received = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe(EventType.OUTBOUND, handler)

    # Start EventBus worker (which runs recovery on startup)
    eventbus_task = bus.start()

    try:
        await asyncio.sleep(0.1)

        assert len(received) == 0
    finally:
        eventbus_task.cancel()
        try:
            await eventbus_task
        except asyncio.CancelledError:
            pass
