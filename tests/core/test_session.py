"""Tests for AgentSession."""

from picklebot.messagebus.telegram_bus import TelegramEventSource


def test_session_add_message(test_agent):
    """Session should add message to in-memory list and persist to history."""
    source = TelegramEventSource(user_id="user_123", chat_id="chat_456")
    session = test_agent.new_session(source=source)

    session.add_message({"role": "user", "content": "Hello"})

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"

    # Verify persisted - Agent has context, AgentSession has shared_context
    messages = test_agent.context.history_store.get_messages(session.session_id)
    assert len(messages) == 1
    assert messages[0].content == "Hello"


def test_session_get_history_limits_messages(test_agent):
    """Session should limit history to max_messages."""
    source = TelegramEventSource(user_id="user_123", chat_id="chat_456")
    session = test_agent.new_session(source=source)

    # Add 5 messages
    for i in range(5):
        session.add_message({"role": "user", "content": f"Message {i}"})

    history = session.get_history(max_messages=3)

    assert len(history) == 3
    assert history[0]["content"] == "Message 2"  # Last 3 messages


def test_session_get_history_uses_max_history(test_agent):
    """Session should use max_history when max_messages not provided."""
    source = TelegramEventSource(user_id="user_123", chat_id="chat_456")
    session = test_agent.new_session(source=source)
    # get_source_settings returns 100 for telegram source
    # Add more messages than max_history
    for i in range(110):
        session.add_message({"role": "user", "content": f"Message {i}"})

    history = session.get_history()

    assert len(history) == 100
    assert history[0]["content"] == "Message 10"  # Last 100 messages
