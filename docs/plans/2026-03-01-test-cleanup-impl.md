# Test Suite Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate duplicate tests, extract common fixtures, and reduce test code by ~370 lines.

**Architecture:** Three-layer approach - first add shared fixtures/helpers, then consolidate files, then apply parametrization patterns.

**Tech Stack:** pytest, pytest-anyio, unittest.mock

---

## Layer 1: Fixtures & Helpers

### Task 1: Create test helpers module

**Files:**
- Create: `tests/helpers.py`

**Step 1: Create helpers.py with definition factories**

```python
"""Test helpers for picklebot test suite."""

from pathlib import Path


def create_test_agent(
    workspace: Path,
    agent_id: str = "test-agent",
    name: str = "Test Agent",
    description: str = "A test agent",
    system_prompt: str = "You are a test assistant.",
    **kwargs,
) -> Path:
    """Create a minimal test agent in workspace.

    Args:
        workspace: Path to workspace directory
        agent_id: Agent identifier (folder name)
        name: Agent display name
        description: Agent description
        system_prompt: Agent system prompt
        **kwargs: Additional frontmatter fields (e.g., max_concurrency)

    Returns:
        Path to the agent directory
    """
    agents_dir = workspace / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    # Build frontmatter
    frontmatter_lines = [
        f"name: {name}",
        f"description: {description}",
    ]
    for key, value in kwargs.items():
        if isinstance(value, str):
            frontmatter_lines.append(f"{key}: {value}")
        else:
            frontmatter_lines.append(f"{key}: {value}")

    frontmatter = "\n".join(frontmatter_lines)

    agent_md = agent_dir / "AGENT.md"
    agent_md.write_text(f"---\n{frontmatter}\n---\n{system_prompt}\n")

    return agent_dir


def create_test_skill(
    workspace: Path,
    skill_id: str = "test-skill",
    name: str = "Test Skill",
    description: str = "A test skill",
    content: str = "# Test Skill\n\nThis is a test skill.",
) -> Path:
    """Create a minimal test skill in workspace.

    Args:
        workspace: Path to workspace directory
        skill_id: Skill identifier (folder name)
        name: Skill display name
        description: Skill description
        content: Skill markdown content

    Returns:
        Path to the skill directory
    """
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_dir = skills_dir / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{content}\n"
    )

    return skill_dir


def create_test_cron(
    workspace: Path,
    cron_id: str = "test-cron",
    name: str = "Test Cron",
    agent: str = "pickle",
    schedule: str = "0 * * * *",
    prompt: str = "Check for updates.",
    one_off: bool = False,
) -> Path:
    """Create a minimal test cron in workspace.

    Args:
        workspace: Path to workspace directory
        cron_id: Cron identifier (folder name)
        name: Cron display name
        agent: Agent to run
        schedule: Cron schedule expression
        prompt: Cron prompt
        one_off: Whether this is a one-off cron

    Returns:
        Path to the cron directory
    """
    crons_dir = workspace / "crons"
    crons_dir.mkdir(parents=True, exist_ok=True)

    cron_dir = crons_dir / cron_id
    cron_dir.mkdir(parents=True, exist_ok=True)

    cron_md = cron_dir / "CRON.md"
    cron_md.write_text(
        f'---\nname: {name}\nagent: {agent}\nschedule: "{schedule}"\none_off: {one_off}\n---\n{prompt}\n'
    )

    return cron_dir
```

**Step 2: Run tests to verify nothing broke**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/helpers.py
git commit -m "test: add definition factory helpers for test setup"
```

---

### Task 2: Add mock_context fixture to conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add mock_context fixture**

Add to `tests/conftest.py`:

```python
from unittest.mock import MagicMock


@pytest.fixture
def mock_context(tmp_path: Path) -> MagicMock:
    """Mock SharedContext for worker tests (no real agent loading)."""
    from picklebot.core.eventbus import EventBus

    context = MagicMock()
    context.config = MagicMock()
    context.config.messagebus = MagicMock()
    context.config.messagebus.telegram = None
    context.config.messagebus.discord = None
    context.config.event_path = tmp_path / ".events"
    context.eventbus = EventBus(context)
    context.messagebus_buses = []
    context.history_store = MagicMock()
    context.history_store.list_sessions = MagicMock(return_value=[])
    return context
```

**Step 2: Run tests to verify nothing broke**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add mock_context fixture for worker tests"
```

---

### Task 3: Add API client fixtures to conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add API client fixtures**

Add imports at top of `tests/conftest.py`:

```python
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
```

Add fixtures:

```python
@pytest.fixture
def api_client(tmp_path: Path):
    """TestClient with pre-configured workspace. Yields (client, workspace)."""
    from picklebot.api import create_app

    # Ensure directories exist
    (tmp_path / "agents").mkdir(exist_ok=True)
    (tmp_path / "skills").mkdir(exist_ok=True)
    (tmp_path / "crons").mkdir(exist_ok=True)

    config = Config(
        workspace=tmp_path,
        llm=LLMConfig(provider="openai", model="gpt-4", api_key="test-key"),
        default_agent="pickle",
    )
    context = SharedContext(config)
    app = create_app(context)

    with TestClient(app) as client:
        yield client, tmp_path


@pytest.fixture
def api_client_with_agent(api_client):
    """TestClient with a test agent already created."""
    from tests.helpers import create_test_agent

    client, workspace = api_client
    create_test_agent(workspace, agent_id="test-agent")
    return client, workspace


@pytest.fixture
def api_client_with_skill(api_client):
    """TestClient with a test skill already created."""
    from tests.helpers import create_test_skill

    client, workspace = api_client
    create_test_skill(workspace, skill_id="test-skill")
    return client, workspace


@pytest.fixture
def api_client_with_cron(api_client):
    """TestClient with a test cron already created."""
    from tests.helpers import create_test_cron

    client, workspace = api_client
    create_test_cron(workspace, cron_id="test-cron")
    return client, workspace
```

**Step 2: Run tests to verify nothing broke**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add API client fixtures for agents, skills, crons"
```

---

## Layer 2: File Consolidation

### Task 4: Merge SharedContext tests

**Files:**
- Modify: `tests/core/test_context.py`
- Delete: `tests/core/test_context_eventbus.py`
- Delete: `tests/core/test_context_buses.py`

**Step 1: Read existing files**

Read `tests/core/test_context_eventbus.py` and `tests/core/test_context_buses.py` content.

**Step 2: Update test_context.py with merged content**

Replace `tests/core/test_context.py` with:

```python
"""Tests for SharedContext."""

from unittest.mock import MagicMock, patch

import pytest

from picklebot.core.context import SharedContext
from picklebot.core.eventbus import EventBus
from picklebot.core.events import InboundEvent, OutboundEvent, Source
from picklebot.core.routing import RoutingTable
from picklebot.messagebus.cli_bus import CliBus
from picklebot.utils.config import Config, LLMConfig


class TestSharedContextBasics:
    """Basic SharedContext initialization tests."""

    def test_context_initialization(self, test_context):
        """SharedContext should initialize with all required components."""
        assert test_context.config is not None
        assert test_context.history_store is not None
        assert test_context.agent_loader is not None
        assert test_context.skill_loader is not None
        assert test_context.cron_loader is not None
        assert test_context.command_registry is not None
        assert test_context.eventbus is not None

    def test_shared_context_has_routing_table(self, test_context):
        """SharedContext should initialize RoutingTable."""
        assert hasattr(test_context, "routing_table")
        assert isinstance(test_context.routing_table, RoutingTable)


class TestSharedContextEventBus:
    """Tests for SharedContext EventBus integration."""

    def test_shared_context_has_eventbus(self, tmp_path):
        """SharedContext should have an EventBus instance initialized."""
        config_file = tmp_path / "config.user.yaml"
        config_file.write_text(
            """default_agent: test-agent
llm:
  provider: openai
  model: gpt-4
  api_key: test
"""
        )

        config = Config.load(tmp_path)
        context = SharedContext(config)
        assert hasattr(context, "eventbus")
        assert isinstance(context.eventbus, EventBus)

    @pytest.mark.asyncio
    async def test_subscribe_by_event_class(self, tmp_path):
        """EventBus.subscribe should accept event classes with type-safe handlers."""
        config_file = tmp_path / "config.user.yaml"
        config_file.write_text(
            """default_agent: test-agent
llm:
  provider: openai
  model: gpt-4
  api_key: test
"""
        )

        config = Config.load(tmp_path)
        context = SharedContext(config)
        eventbus = context.eventbus

        received_inbound = []
        received_outbound = []

        async def inbound_handler(event: InboundEvent):
            received_inbound.append(event)

        async def outbound_handler(event: OutboundEvent):
            received_outbound.append(event)

        # Subscribe by event class
        eventbus.subscribe(InboundEvent, inbound_handler)
        eventbus.subscribe(OutboundEvent, outbound_handler)

        # Create test events
        inbound = InboundEvent(
            session_id="test",
            agent_id="test",
            content="inbound",
            source=Source.platform("telegram", "user1"),
        )
        outbound = OutboundEvent(
            session_id="test",
            agent_id="test",
            content="outbound",
            source=Source.agent("test"),
        )

        # Notify subscribers
        await eventbus._notify_subscribers(inbound)
        await eventbus._notify_subscribers(outbound)

        # Verify correct handlers called
        assert len(received_inbound) == 1
        assert received_inbound[0].content == "inbound"
        assert len(received_outbound) == 1
        assert received_outbound[0].content == "outbound"


class TestSharedContextCustomBuses:
    """Tests for optional buses parameter in SharedContext.__init__."""

    @pytest.fixture
    def mock_config(self, tmp_path):
        """Config without any messagebus enabled."""
        return Config(
            workspace=tmp_path,
            llm=LLMConfig(provider="openai", model="gpt-4", api_key="test-key"),
            default_agent="test",
        )

    def test_accepts_buses_parameter(self, mock_config):
        """SharedContext should accept optional buses parameter."""
        cli_bus = CliBus()
        context = SharedContext(config=mock_config, buses=[cli_bus])

        assert context.messagebus_buses == [cli_bus]

    def test_uses_provided_buses_when_given(self, mock_config):
        """When buses are provided, they should be used directly."""
        cli_bus = CliBus()
        context = SharedContext(config=mock_config, buses=[cli_bus])

        assert len(context.messagebus_buses) == 1
        assert context.messagebus_buses[0] is cli_bus

    def test_backward_compatible_loads_from_config_when_buses_none(self, mock_config):
        """When buses=None (default), should load from config like before."""
        with patch("picklebot.core.context.MessageBus.from_config") as mock_from_config:
            mock_from_config.return_value = []

            context = SharedContext(config=mock_config, buses=None)

            mock_from_config.assert_called_once_with(mock_config)
            assert context.messagebus_buses == []

    def test_backward_compatible_default_behavior(self, mock_config):
        """Without buses parameter, should load from config (backward compat)."""
        with patch("picklebot.core.context.MessageBus.from_config") as mock_from_config:
            mock_from_config.return_value = []

            context = SharedContext(config=mock_config)

            mock_from_config.assert_called_once_with(mock_config)
            assert context.messagebus_buses == []

    def test_empty_buses_list_is_used_not_config(self, mock_config):
        """Empty list should be used, not fall back to config."""
        with patch("picklebot.core.context.MessageBus.from_config") as mock_from_config:
            mock_from_config.return_value = [MagicContext()]

            context = SharedContext(config=mock_config, buses=[])

            mock_from_config.assert_not_called()
            assert context.messagebus_buses == []

    def test_multiple_buses_accepted(self, mock_config):
        """Multiple buses can be passed."""
        bus1 = CliBus()
        bus2 = CliBus()

        context = SharedContext(config=mock_config, buses=[bus1, bus2])

        assert len(context.messagebus_buses) == 2
        assert context.messagebus_buses[0] is bus1
        assert context.messagebus_buses[1] is bus2
```

**Step 3: Delete the old files**

```bash
rm tests/core/test_context_eventbus.py tests/core/test_context_buses.py
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/core/test_context.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/core/test_context.py
git rm tests/core/test_context_eventbus.py tests/core/test_context_buses.py
git commit -m "refactor(test): merge SharedContext tests into single file"
```

---

### Task 5: Merge event type tests

**Files:**
- Modify: `tests/events/test_types.py` (absorb content from test_events.py)
- Delete: `tests/core/test_events.py`

**Step 1: Read both event test files**

Read `tests/core/test_events.py` and `tests/events/test_types.py` to identify duplicates.

**Step 2: Update test_types.py with consolidated content**

The file should contain all event type tests, with duplicates removed. Key deduplication:
- Remove duplicate `test_deserialize_uses_class_name_not_enum_value` (keep one)
- Consolidate roundtrip tests

**Step 3: Delete the old file**

```bash
rm tests/core/test_events.py
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/events/test_types.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/events/test_types.py
git rm tests/core/test_events.py
git commit -m "refactor(test): consolidate event type tests, remove duplicates"
```

---

### Task 6: Merge DeliveryWorker tests

**Files:**
- Modify: `tests/server/test_delivery_worker.py`
- Delete: `tests/events/test_delivery.py`

**Step 1: Read both files**

Read `tests/events/test_delivery.py` and `tests/server/test_delivery_worker.py`.

**Step 2: Update test_delivery_worker.py with merged content**

Merge unique tests from test_delivery.py:
- Keep `test_delivery_worker_has_lru_cache`
- Keep `test_get_session_source_returns_session`
- Keep `test_get_session_source_returns_none_if_not_found`
- Keep `test_handle_event_skips_if_no_source`
- Keep `test_handle_event_delivers_to_platform`
- Add `test_chunk_message_*` tests from test_delivery.py
- Add `test_platform_limits` from test_delivery.py
- Remove duplicate `mock_context` fixture (use conftest)

**Step 3: Delete the old file**

```bash
rm tests/events/test_delivery.py
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/server/test_delivery_worker.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/server/test_delivery_worker.py
git rm tests/events/test_delivery.py
git commit -m "refactor(test): merge DeliveryWorker tests, use shared mock_context"
```

---

### Task 7: Update API tests to use shared fixtures

**Files:**
- Modify: `tests/api/test_agents.py`
- Modify: `tests/api/test_skills.py`
- Modify: `tests/api/test_crons.py`

**Step 1: Update test_agents.py**

Replace the `client` fixture with:

```python
@pytest.fixture
def client(api_client_with_agent):
    """Create test client with test agent."""
    client, _ = api_client_with_agent
    return client
```

**Step 2: Update test_skills.py**

Replace the `client` fixture with:

```python
@pytest.fixture
def client(api_client_with_skill):
    """Create test client with test skill."""
    client, _ = api_client_with_skill
    return client
```

**Step 3: Update test_crons.py**

Replace the `client` fixture with:

```python
@pytest.fixture
def client(api_client_with_cron):
    """Create test client with test cron."""
    client, _ = api_client_with_cron
    return client
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/api/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/api/test_agents.py tests/api/test_skills.py tests/api/test_crons.py
git commit -m "refactor(test): use shared API client fixtures in API tests"
```

---

## Layer 3: Test Patterns

### Task 8: Add parametrized MessageBus lifecycle tests

**Files:**
- Modify: `tests/messagebus/test_base.py`

**Step 1: Add lifecycle test helper factory**

Add to `tests/messagebus/test_base.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def _create_mock_telegram_app():
    """Create a mock Telegram Application for testing."""
    mock_app = MagicMock()
    mock_app.updater = MagicMock()
    mock_app.updater.running = True
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()
    mock_app.initialize = AsyncMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.add_handler = MagicMock()
    mock_app.bot = MagicMock()
    return mock_app


def _create_mock_discord_client():
    """Create a mock Discord Client for testing."""
    mock_client = MagicMock()
    mock_client.start = AsyncMock()
    mock_client.close = AsyncMock()
    return mock_client


def _get_bus_and_mock(bus_type: str):
    """Get bus instance and mock for the given platform type."""
    if bus_type == "telegram":
        from picklebot.messagebus.telegram_bus import TelegramBus
        from picklebot.utils.config import TelegramConfig

        config = TelegramConfig(bot_token="test_token")
        bus = TelegramBus(config)
        mock = _create_mock_telegram_app()
        return bus, mock, "picklebot.messagebus.telegram_bus.Application.builder"
    else:
        from picklebot.messagebus.discord_bus import DiscordBus
        from picklebot.utils.config import DiscordConfig

        config = DiscordConfig(bot_token="test_token")
        bus = DiscordBus(config)
        mock = _create_mock_discord_client()
        return bus, mock, "picklebot.messagebus.discord_bus.discord.Client"
```

**Step 2: Add parametrized lifecycle tests**

Add test class:

```python
@pytest.mark.parametrize("bus_type", ["telegram", "discord"])
class TestMessageBusLifecycle:
    """Shared lifecycle tests for all bus implementations."""

    @pytest.mark.anyio
    async def test_run_stop_lifecycle(self, bus_type):
        """Test that bus can run and stop."""
        bus, mock, patch_path = _get_bus_and_mock(bus_type)

        async def dummy_callback(content, context):
            pass

        if bus_type == "telegram":
            with patch(patch_path) as mock_builder:
                mock_builder.return_value.token.return_value.build.return_value = mock
                run_task = asyncio.create_task(bus.run(dummy_callback))
                await asyncio.sleep(0.1)
                await bus.stop()
                await run_task

                mock.initialize.assert_called_once()
                mock.start.assert_called_once()
        else:
            with patch(patch_path, return_value=mock):
                await bus.run(dummy_callback)
                await bus.stop()

                mock.start.assert_called_once()
                mock.close.assert_called_once()

    @pytest.mark.anyio
    async def test_run_raises_on_second_call(self, bus_type):
        """Calling run twice should raise RuntimeError."""
        bus, mock, patch_path = _get_bus_and_mock(bus_type)

        async def dummy_callback(content, context):
            pass

        with patch(patch_path, return_value=mock) if bus_type == "discord" else patch(patch_path) as mock_builder:
            if bus_type == "telegram":
                mock_builder.return_value.token.return_value.build.return_value = mock

            await bus.run(dummy_callback)

            with pytest.raises(RuntimeError, match=f"{bus_type.capitalize()}Bus already running"):
                await bus.run(dummy_callback)

    @pytest.mark.anyio
    async def test_stop_is_idempotent(self, bus_type):
        """Calling stop twice should be safe - second call is no-op."""
        bus, mock, patch_path = _get_bus_and_mock(bus_type)

        async def dummy_callback(content, context):
            pass

        with patch(patch_path, return_value=mock) if bus_type == "discord" else patch(patch_path) as mock_builder:
            if bus_type == "telegram":
                mock_builder.return_value.token.return_value.build.return_value = mock

            await bus.run(dummy_callback)
            await bus.stop()
            await bus.stop()  # Second call should be no-op

            if bus_type == "telegram":
                mock.stop.assert_called_once()
            else:
                mock.close.assert_called_once()

    @pytest.mark.anyio
    async def test_stop_without_run_is_safe(self, bus_type):
        """Calling stop without run should be safe - no-op."""
        bus, _, _ = _get_bus_and_mock(bus_type)

        await bus.stop()  # Should not raise

    @pytest.mark.anyio
    async def test_can_rerun_after_stop(self, bus_type):
        """Should be able to run again after stop."""
        bus, mock, patch_path = _get_bus_and_mock(bus_type)

        async def dummy_callback(content, context):
            pass

        with patch(patch_path, return_value=mock) if bus_type == "discord" else patch(patch_path) as mock_builder:
            if bus_type == "telegram":
                mock_builder.return_value.token.return_value.build.return_value = mock

            # First cycle
            await bus.run(dummy_callback)
            await bus.stop()

            if bus_type == "telegram":
                mock.initialize.reset_mock()
            else:
                mock.start.reset_mock()

            # Second cycle should work
            await bus.run(dummy_callback)
            if bus_type == "telegram":
                mock.initialize.assert_called_once()

            await bus.stop()
```

Add import at top:

```python
import asyncio
```

**Step 3: Run tests to verify**

Run: `uv run pytest tests/messagebus/test_base.py -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/messagebus/test_base.py
git commit -m "refactor(test): add parametrized MessageBus lifecycle tests"
```

---

### Task 9: Remove duplicate lifecycle tests from platform-specific files

**Files:**
- Modify: `tests/messagebus/test_telegram_bus.py`
- Modify: `tests/messagebus/test_discord_bus.py`

**Step 1: Remove duplicate tests from test_telegram_bus.py**

Remove these tests (now covered by parametrized tests in test_base.py):
- `test_run_stop_lifecycle`
- `test_run_raises_on_second_call`
- `test_stop_is_idempotent`
- `test_stop_without_run_is_safe`
- `test_can_rerun_after_stop`
- `_create_mock_telegram_app` helper

Keep only:
- `test_telegram_bus_platform_name`
- `TestTelegramBusReply` class
- `TestTelegramBusPost` class

**Step 2: Remove duplicate tests from test_discord_bus.py**

Remove these tests (now covered by parametrized tests in test_base.py):
- `test_run_stop_lifecycle`
- `test_run_raises_on_second_call`
- `test_stop_is_idempotent`
- `test_stop_without_run_is_safe`
- `test_can_rerun_after_stop`
- `_create_mock_discord_client` helper

Keep only:
- `test_discord_bus_platform_name`
- `TestDiscordBusReply` class
- `TestDiscordBusPost` class

**Step 3: Run tests to verify**

Run: `uv run pytest tests/messagebus/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/messagebus/test_telegram_bus.py tests/messagebus/test_discord_bus.py
git commit -m "refactor(test): remove duplicate lifecycle tests, use parametrized base"
```

---

### Task 10: Update test_agent_worker.py to use helpers

**Files:**
- Modify: `tests/server/test_agent_worker.py`

**Step 1: Replace inline agent creation with helper**

Replace patterns like:

```python
agents_dir = tmp_path / "agents"
agents_dir.mkdir(parents=True)
test_agent_dir = agents_dir / "test-agent"
test_agent_dir.mkdir(parents=True)

agent_md = test_agent_dir / "AGENT.md"
agent_md.write_text(
    """---
name: Test Agent
description: A test agent
---
You are a test assistant. Respond briefly.
"""
)
```

With:

```python
from tests.helpers import create_test_agent

create_test_agent(tmp_path, agent_id="test-agent")
```

**Step 2: Run tests to verify**

Run: `uv run pytest tests/server/test_agent_worker.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/server/test_agent_worker.py
git commit -m "refactor(test): use create_test_agent helper in agent_worker tests"
```

---

### Task 11: Final verification and cleanup

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 2: Run linting**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 3: Count lines reduced**

Run: `wc -l tests/**/*.py 2>/dev/null | tail -1`

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "style: format test files after cleanup"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Create test helpers module |
| 2 | Add mock_context fixture |
| 3 | Add API client fixtures |
| 4 | Merge SharedContext tests (3 → 1) |
| 5 | Merge event type tests (2 → 1) |
| 6 | Merge DeliveryWorker tests (2 → 1) |
| 7 | Update API tests to use shared fixtures |
| 8 | Add parametrized MessageBus lifecycle tests |
| 9 | Remove duplicate lifecycle tests from platform files |
| 10 | Update agent_worker tests to use helpers |
| 11 | Final verification |
