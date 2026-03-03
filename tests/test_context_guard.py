# tests/test_context_guard.py
"""Tests for ContextGuard."""

from picklebot.core.context_guard import ContextGuard


class TestContextGuard:
    def test_context_guard_exists(self):
        """ContextGuard can be instantiated."""
        guard = ContextGuard(shared_context=None, token_threshold=1000)
        assert guard.token_threshold == 1000
