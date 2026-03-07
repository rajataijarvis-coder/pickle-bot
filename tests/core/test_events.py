"""Tests for Event classes after agent_id removal."""
import pytest
import time
from picklebot.core.events import (
    Event,
    InboundEvent,
    OutboundEvent,
    DispatchEvent,
    DispatchResultEvent,
    AgentEventSource,
    CliEventSource,
)


def test_event_base_class_has_no_agent_id():
    """Event base class should not have agent_id field."""
    source = CliEventSource()
    event = Event(
        session_id="test-session",
        source=source,
        content="test content",
    )

    # Should not have agent_id attribute
    assert not hasattr(event, "agent_id")

    # Should have required fields
    assert event.session_id == "test-session"
    assert event.source == source
    assert event.content == "test content"
    assert isinstance(event.timestamp, float)


def test_inbound_event_creation():
    """InboundEvent should be creatable without agent_id."""
    source = CliEventSource()
    event = InboundEvent(
        session_id="test-session",
        source=source,
        content="user message",
        retry_count=0,
    )

    assert event.session_id == "test-session"
    assert event.source == source
    assert event.content == "user message"
    assert event.retry_count == 0
    assert not hasattr(event, "agent_id")


def test_dispatch_event_creation():
    """DispatchEvent should be creatable without agent_id."""
    source = AgentEventSource(agent_id="pickle")
    event = DispatchEvent(
        session_id="test-session",
        source=source,
        content="dispatch task",
        parent_session_id="parent-123",
    )

    assert event.session_id == "test-session"
    assert event.source == source
    assert event.content == "dispatch task"
    assert event.parent_session_id == "parent-123"
    assert not hasattr(event, "agent_id")


def test_outbound_event_creation():
    """OutboundEvent should be creatable without agent_id."""
    source = AgentEventSource(agent_id="pickle")
    event = OutboundEvent(
        session_id="test-session",
        source=source,
        content="response",
        error=None,
    )

    assert event.session_id == "test-session"
    assert event.source == source
    assert event.content == "response"
    assert event.error is None
    assert not hasattr(event, "agent_id")


def test_dispatch_result_event_creation():
    """DispatchResultEvent should be creatable without agent_id."""
    source = AgentEventSource(agent_id="pickle")
    event = DispatchResultEvent(
        session_id="test-session",
        source=source,
        content="result",
        error=None,
    )

    assert event.session_id == "test-session"
    assert event.source == source
    assert event.content == "result"
    assert event.error is None
    assert not hasattr(event, "agent_id")


def test_event_serialization_without_agent_id():
    """Event should serialize without agent_id field."""
    source = CliEventSource()
    event = InboundEvent(
        session_id="test-session",
        source=source,
        content="test",
    )

    data = event.to_dict()

    assert "agent_id" not in data
    assert data["session_id"] == "test-session"
    assert data["source"] == "platform-cli:cli-user"
    assert data["content"] == "test"
    assert data["type"] == "InboundEvent"
