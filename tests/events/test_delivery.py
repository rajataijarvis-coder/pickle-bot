# tests/events/test_delivery.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from picklebot.events.delivery import chunk_message, DeliveryWorker
from picklebot.events.types import Event, EventType
from picklebot.events.bus import EventBus


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.config = MagicMock()
    context.config.runtime = {}
    context.eventbus = EventBus()
    # Mock platform buses
    context.telegram_bus = AsyncMock()
    context.discord_bus = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_delivery_worker_creation(mock_context):
    worker = DeliveryWorker(mock_context)
    assert worker.context == mock_context


@pytest.mark.asyncio
async def test_delivery_worker_handles_outbound_event(mock_context):
    worker = DeliveryWorker(mock_context)

    # Mock the lookup
    worker._lookup_platform = MagicMock(
        return_value={
            "platform": "telegram",
            "chat_id": "123456",
        }
    )

    event = Event(
        type=EventType.OUTBOUND,
        session_id="test-session",
        content="Hello",
        source="agent:pickle",
        timestamp=12345.0,
    )

    await worker.handle_event(event)

    # Should have called telegram bus send
    mock_context.telegram_bus.send.assert_called_once_with("123456", "Hello")


@pytest.mark.asyncio
async def test_delivery_worker_handles_cli_platform(mock_context, capsys):
    worker = DeliveryWorker(mock_context)

    # Mock the lookup for CLI
    worker._lookup_platform = MagicMock(
        return_value={
            "platform": "cli",
        }
    )

    event = Event(
        type=EventType.OUTBOUND,
        session_id="test-session",
        content="Hello CLI",
        source="agent:pickle",
        timestamp=12345.0,
    )

    await worker.handle_event(event)

    # Should print to stdout
    captured = capsys.readouterr()
    assert "Hello CLI" in captured.out


def test_chunk_message_under_limit():
    result = chunk_message("Hello world", limit=100)
    assert result == ["Hello world"]


def test_chunk_message_exact_limit():
    message = "x" * 100
    result = chunk_message(message, limit=100)
    assert result == [message]


def test_chunk_message_splits_at_paragraph():
    message = "Para one\n\nPara two\n\nPara three"
    result = chunk_message(message, limit=15)
    # "Para one" = 8 chars
    # "Para two" = 8 chars
    # "Para three" = 10 chars
    assert len(result) == 3
    assert "Para one" in result[0]
    assert "Para two" in result[1]


def test_chunk_message_hard_split():
    message = "A" * 50  # Single long "paragraph"
    result = chunk_message(message, limit=20)
    assert len(result) == 3
    assert len(result[0]) == 20
    assert len(result[1]) == 20
    assert len(result[2]) == 10


def test_chunk_message_mixed():
    message = "Short\n\n" + "B" * 50 + "\n\nEnd"
    result = chunk_message(message, limit=20)
    # "Short" = 5 chars - chunk 1
    # 50 B's - chunks 2,3,4 (20+20+10)
    # "End" = 3 chars - chunk 5
    assert len(result) >= 3


def test_platform_limits():
    from picklebot.events.delivery import PLATFORM_LIMITS

    assert PLATFORM_LIMITS["telegram"] == 4096
    assert PLATFORM_LIMITS["discord"] == 2000
    assert PLATFORM_LIMITS["cli"] == float("inf")
