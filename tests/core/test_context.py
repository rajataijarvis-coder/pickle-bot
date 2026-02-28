"""Tests for SharedContext."""


def test_context_initialization(test_context):
    """SharedContext should initialize with all required components."""
    assert test_context.config is not None
    assert test_context.history_store is not None
    assert test_context.agent_loader is not None
    assert test_context.skill_loader is not None
    assert test_context.cron_loader is not None
    assert test_context.command_registry is not None
    assert test_context.eventbus is not None
