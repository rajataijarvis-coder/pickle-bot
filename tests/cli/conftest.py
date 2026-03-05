"""Fixtures for CLI tests."""

from pathlib import Path
import pytest

from picklebot.utils.config import Config, LLMConfig


@pytest.fixture
def test_config_with_agent(tmp_path: Path) -> Config:
    """Config with workspace pointing to tmp_path and a test agent created."""
    # Create a test agent
    from tests.helpers import create_test_agent

    create_test_agent(tmp_path, agent_id="test", name="Test Agent")

    llm_config = LLMConfig(provider="openai", model="gpt-4", api_key="test-key")
    return Config(workspace=tmp_path, llm=llm_config, default_agent="test")
