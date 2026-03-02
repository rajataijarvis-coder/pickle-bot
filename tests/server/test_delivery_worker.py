import pytest
from unittest.mock import Mock, AsyncMock, patch
from picklebot.server.delivery_worker import DeliveryWorker
from picklebot.core.events import OutboundEvent


@pytest.fixture
def mock_context():
    context = Mock()
    context.config = Mock()
    context.config.messagebus = Mock()

    context.history_store = Mock()
    context.eventbus = Mock()
    context.eventbus.subscribe = Mock()
    context.eventbus.ack = Mock()

    context.messagebus_buses = []

    return context


def test_delivery_worker_has_lru_cache(mock_context):
    """DeliveryWorker should use LRU cache for session lookup."""
    worker = DeliveryWorker(mock_context)

    # Check that _get_session_source is decorated with lru_cache
    assert hasattr(worker._get_session_source, "cache_info")


def test_get_session_source_returns_session(mock_context):
    """_get_session_source should return session with source."""
    from picklebot.core.history import HistorySession

    mock_session = HistorySession(
        id="session-123",
        agent_id="pickle",
        source="telegram:123456",
        created_at="2026-03-01T10:00:00",
        updated_at="2026-03-01T10:00:00",
    )
    mock_context.history_store.list_sessions.return_value = [mock_session]

    worker = DeliveryWorker(mock_context)
    result = worker._get_session_source("session-123")

    assert result == mock_session
    assert result.source == "telegram:123456"


def test_get_session_source_returns_none_if_not_found(mock_context):
    """_get_session_source should return None if session not found."""
    mock_context.history_store.list_sessions.return_value = []

    worker = DeliveryWorker(mock_context)
    result = worker._get_session_source("unknown-session")

    assert result is None


@pytest.mark.asyncio
async def test_handle_event_skips_if_no_source(mock_context):
    """handle_event should skip delivery if session has no source."""
    mock_context.history_store.list_sessions.return_value = []

    worker = DeliveryWorker(mock_context)
    event = OutboundEvent(
        session_id="unknown",
        agent_id="pickle",
        source="agent:pickle",
        content="Hello",
    )

    await worker.handle_event(event)

    # Should not ack since we skipped
    mock_context.eventbus.ack.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_delivers_to_platform(mock_context):
    """handle_event should deliver to platform from session source."""
    from picklebot.core.history import HistorySession
    from picklebot.messagebus.telegram_bus import TelegramContext

    mock_session = HistorySession(
        id="session-123",
        agent_id="pickle",
        source="telegram:123456",
        created_at="2026-03-01T10:00:00",
        updated_at="2026-03-01T10:00:00",
    )
    mock_context.history_store.list_sessions.return_value = [mock_session]

    mock_bus = Mock()
    mock_bus.platform_name = "telegram"
    mock_bus.reply = AsyncMock()
    mock_context.messagebus_buses = [mock_bus]

    worker = DeliveryWorker(mock_context)
    event = OutboundEvent(
        session_id="session-123",
        agent_id="pickle",
        source="agent:pickle",
        content="Hello",
    )

    await worker.handle_event(event)

    mock_bus.reply.assert_called_once()
    mock_context.eventbus.ack.assert_called_once_with(event)
