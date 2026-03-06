"""Tests for WebSocketEventSource."""

import pytest
from picklebot.core.events import WebSocketEventSource


class TestWebSocketEventSource:
    """Test WebSocketEventSource functionality."""

    def test_create_websocket_event_source(self):
        """Test creating WebSocketEventSource with user_id."""
        source = WebSocketEventSource(user_id="user-123")

        assert source.user_id == "user-123"
        assert source.is_platform is True
        assert source.is_agent is False
        assert source.is_cron is False

    def test_string_representation(self):
        """Test string representation of WebSocketEventSource."""
        source = WebSocketEventSource(user_id="user-456")

        assert str(source) == "platform-ws:user-456"

    def test_from_string_valid(self):
        """Test parsing valid source string."""
        source = WebSocketEventSource.from_string("platform-ws:user-789")

        assert source.user_id == "user-789"

    def test_from_string_with_colon_in_user_id(self):
        """Test parsing source string with colon in user_id."""
        source = WebSocketEventSource.from_string("platform-ws:user:with:colons")

        assert source.user_id == "user:with:colons"

    def test_from_string_invalid_namespace(self):
        """Test parsing with invalid namespace."""
        with pytest.raises(ValueError, match="Invalid WebSocketEventSource"):
            WebSocketEventSource.from_string("invalid-namespace:user-123")

    def test_from_string_invalid_format(self):
        """Test parsing with invalid format (no colon)."""
        with pytest.raises(ValueError, match="Invalid WebSocketEventSource"):
            WebSocketEventSource.from_string("invalid-format")

    def test_from_string_empty_user_id(self):
        """Test parsing with empty user_id."""
        with pytest.raises(ValueError, match="Invalid WebSocketEventSource"):
            WebSocketEventSource.from_string("platform-ws:")
