# Session-Aware Commands Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move slash command dispatch from ChannelWorker to AgentWorker, enabling commands to access AgentSession for operations like compaction, agent switching, and session management.

**Architecture:** Commands receive AgentSession instead of SharedContext, accessing shared resources via `session.shared_context`. Command dispatch happens in AgentWorker after session is loaded. Two new RoutingTable methods manage runtime bindings and session cache.

**Tech Stack:** Python 3.11+, pytest, asyncio

**Design Doc:** `docs/plans/2026-03-06-session-aware-commands-design.md`

---

## Task 1: Add RoutingTable Methods

**Files:**
- Modify: `src/picklebot/core/routing.py`
- Modify: `tests/core/test_routing.py`

**Step 1: Write failing tests for RoutingTable.add_runtime_binding**

Add to `tests/core/test_routing.py`:

```python
def test_add_runtime_binding(routing_table, mock_context):
    """Test adding runtime binding."""
    # Setup: no existing bindings
    mock_context.config.routing = {"bindings": []}

    # Add binding
    routing_table.add_runtime_binding(
        "platform-telegram:user_123:chat_456",
        "cookie"
    )

    # Verify binding added
    bindings = mock_context.config.routing["bindings"]
    assert len(bindings) == 1
    assert bindings[0]["agent"] == "cookie"
    assert bindings[0]["value"] == "platform-telegram:user_123:chat_456"

    # Verify cache cleared (forces reload)
    assert routing_table._bindings is None


def test_add_runtime_binding_appends_existing(routing_table, mock_context):
    """Test adding binding appends to existing bindings."""
    # Setup: existing binding
    mock_context.config.routing = {
        "bindings": [{"agent": "pickle", "value": "platform-cli:.*"}]
    }

    # Add new binding
    routing_table.add_runtime_binding(
        "platform-telegram:user_123:chat_456",
        "cookie"
    )

    # Verify both bindings present
    bindings = mock_context.config.routing["bindings"]
    assert len(bindings) == 2
    assert bindings[0]["agent"] == "pickle"
    assert bindings[1]["agent"] == "cookie"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_routing.py::test_add_runtime_binding -xvs`
Expected: FAIL with AttributeError: 'RoutingTable' object has no attribute 'add_runtime_binding'

**Step 3: Implement RoutingTable.add_runtime_binding**

Add to `src/picklebot/core/routing.py` in `RoutingTable` class:

```python
def add_runtime_binding(self, source_pattern: str, agent_id: str) -> None:
    """
    Add a runtime routing binding.

    Args:
        source_pattern: Source pattern to match
        agent_id: Agent to route to
    """
    # Get existing bindings
    bindings = self._context.config.routing.get("bindings", [])

    # Add new binding
    bindings.append({
        "agent": agent_id,
        "value": source_pattern
    })

    # Update runtime config
    self._context.config.set_runtime("routing.bindings", bindings)

    # Clear cache to force reload
    self._bindings = None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_routing.py::test_add_runtime_binding -xvs`
Expected: PASS

**Step 5: Write failing test for RoutingTable.clear_session_cache**

Add to `tests/core/test_routing.py`:

```python
def test_clear_session_cache(routing_table, mock_context):
    """Test clearing session cache for a source."""
    # Setup: source has cached session
    source_str = "platform-telegram:user_123:chat_456"
    mock_context.config.sources = {
        source_str: {"session_id": "existing-session-123"}
    }

    # Clear cache
    routing_table.clear_session_cache(source_str)

    # Verify source removed
    assert source_str not in mock_context.config.sources


def test_clear_session_cache_nonexistent(routing_table, mock_context):
    """Test clearing cache for nonexistent source is safe."""
    # Setup: no sources
    mock_context.config.sources = {}

    # Clear nonexistent source (should not error)
    routing_table.clear_session_cache("platform-telegram:user:chat")

    # Verify still empty
    assert len(mock_context.config.sources) == 0
```

**Step 6: Run test to verify it fails**

Run: `pytest tests/core/test_routing.py::test_clear_session_cache -xvs`
Expected: FAIL with AttributeError: 'RoutingTable' object has no attribute 'clear_session_cache'

**Step 7: Implement RoutingTable.clear_session_cache**

Add to `src/picklebot/core/routing.py` in `RoutingTable` class:

```python
def clear_session_cache(self, source_str: str) -> None:
    """
    Clear session cache for a source.

    Args:
        source_str: Source string to clear
    """
    if source_str in self._context.config.sources:
        # Remove from sources dict
        del self._context.config.sources[source_str]

        # Persist to runtime config
        self._context.config.set_runtime("sources", self._context.config.sources)
```

**Step 8: Run tests to verify they pass**

Run: `pytest tests/core/test_routing.py::test_clear_session_cache -xvs`
Expected: PASS

**Step 9: Commit**

```bash
git add src/picklebot/core/routing.py tests/core/test_routing.py
git commit -m "feat: add RoutingTable methods for runtime binding and cache management"
```

---

## Task 2: Update Command Base Class

**Files:**
- Modify: `src/picklebot/core/commands/base.py`
- Modify: `tests/core/commands/test_base.py`

**Step 1: Write test for updated Command signature**

Add to `tests/core/commands/test_base.py`:

```python
from picklebot.core.commands.base import Command


class MockCommand(Command):
    """Test command implementation."""
    name = "test"
    description = "Test command"

    def execute(self, args: str, session) -> str:
        return f"Executed with session: {session.session_id}"


def test_command_execute_receives_session(mock_session):
    """Test that execute receives AgentSession."""
    cmd = MockCommand()

    result = cmd.execute("test-args", mock_session)

    assert "session-" in result
    assert mock_session.session_id in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/commands/test_base.py::test_command_execute_receives_session -xvs`
Expected: FAIL with signature mismatch or type error

**Step 3: Update Command base class**

Modify `src/picklebot/core/commands/base.py`:

```python
"""Base classes for slash commands."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picklebot.core.agent import AgentSession


class Command(ABC):
    """Base class for slash commands."""

    name: str
    aliases: list[str] = []
    description: str = ""

    @abstractmethod
    def execute(self, args: str, session: "AgentSession") -> str:
        """Execute the command and return response string."""
        pass
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/commands/test_base.py::test_command_execute_receives_session -xvs`
Expected: PASS (after updating test imports and fixtures)

**Step 5: Commit**

```bash
git add src/picklebot/core/commands/base.py tests/core/commands/test_base.py
git commit -m "refactor: update Command base class to receive AgentSession"
```

---

## Task 3: Update Existing Commands

**Files:**
- Modify: `src/picklebot/core/commands/handlers.py`
- Modify: `tests/core/commands/test_handlers.py`

**Step 1: Update tests for existing commands**

Update `tests/core/commands/test_handlers.py` to use `mock_session`:

```python
def test_help_command_with_session(mock_session):
    """Test help command with session context."""
    cmd = HelpCommand()
    result = cmd.execute("", mock_session)
    assert "**Available Commands:**" in result


def test_agent_command_list_with_session(mock_session, mock_context):
    """Test agent command lists agents."""
    cmd = AgentCommand()
    result = cmd.execute("", mock_session)
    assert "**Agents:**" in result
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/commands/test_handlers.py -xvs`
Expected: FAIL with signature mismatch

**Step 3: Update HelpCommand**

Modify `src/picklebot/core/commands/handlers.py`:

```python
class HelpCommand(Command):
    """Show available commands."""

    name = "help"
    aliases = ["?"]
    description = "Show available commands"

    def execute(self, args: str, session: AgentSession) -> str:
        lines = ["**Available Commands:**"]
        for cmd in session.shared_context.command_registry.list_commands():
            names = [f"/{cmd.name}"] + [f"/{a}" for a in cmd.aliases]
            lines.append(f"{', '.join(names)} - {cmd.description}")
        return "\n".join(lines)
```

**Step 4: Update AgentCommand**

```python
class AgentCommand(Command):
    """List agents or switch agent."""

    name = "agent"
    aliases = ["agents"]
    description = "Switch to a different agent (starts fresh session)"

    def execute(self, args: str, session: AgentSession) -> str:
        if not args:
            # List agents
            agents = session.shared_context.agent_loader.discover_agents()
            lines = ["**Agents:**"]
            for agent in agents:
                marker = " (current)" if agent.id == session.agent.agent_def.id else ""
                lines.append(f"- `{agent.id}`: {agent.name}{marker}")
            return "\n".join(lines)

        # Switch agent
        agent_id = args.strip()
        source_str = str(session.source)

        # Verify agent exists
        try:
            session.shared_context.agent_loader.load(agent_id)
        except ValueError:
            return f"✗ Agent `{agent_id}` not found."

        # Add runtime binding + clear cache
        routing = session.shared_context.routing_table
        routing.add_runtime_binding(source_str, agent_id)
        routing.clear_session_cache(source_str)

        return f"✓ Switched to `{agent_id}`. Next message starts fresh conversation."
```

**Step 5: Update SkillsCommand**

```python
class SkillsCommand(Command):
    """List all skills."""

    name = "skills"
    description = "List all skills"

    def execute(self, args: str, session: AgentSession) -> str:
        skills = session.shared_context.skill_loader.discover_skills()
        if not skills:
            return "No skills configured."

        lines = ["**Skills:**"]
        for skill in skills:
            lines.append(f"- `{skill.id}`: {skill.description}")
        return "\n".join(lines)
```

**Step 6: Update CronsCommand**

```python
class CronsCommand(Command):
    """List all cron jobs."""

    name = "crons"
    description = "List all cron jobs"

    def execute(self, args: str, session: AgentSession) -> str:
        crons = session.shared_context.cron_loader.discover_crons()
        if not crons:
            return "No cron jobs configured."

        lines = ["**Cron Jobs:**"]
        for cron in crons:
            lines.append(f"- `{cron.id}`: {cron.schedule}")
        return "\n".join(lines)
```

**Step 7: Run tests to verify they pass**

Run: `pytest tests/core/commands/test_handlers.py -xvs`
Expected: PASS

**Step 8: Commit**

```bash
git add src/picklebot/core/commands/handlers.py tests/core/commands/test_handlers.py
git commit -m "refactor: update existing commands to use AgentSession"
```

---

## Task 4: Add New Commands

**Files:**
- Modify: `src/picklebot/core/commands/handlers.py`
- Modify: `tests/core/commands/test_handlers.py`

**Step 1: Write tests for CompactCommand**

Add to `tests/core/commands/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_compact_command(mock_session):
    """Test compact command triggers compaction."""
    cmd = CompactCommand()
    result = await cmd.execute("", mock_session)
    assert "✓ Context compacted" in result
    assert "messages retained" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/commands/test_handlers.py::test_compact_command -xvs`
Expected: FAIL with ImportError or NameError

**Step 3: Implement CompactCommand**

Add to `src/picklebot/core/commands/handlers.py`:

```python
class CompactCommand(Command):
    """Trigger manual context compaction."""

    name = "compact"
    description = "Compact conversation context manually"

    async def execute(self, args: str, session: AgentSession) -> str:
        # Force compaction via context_guard
        session.state = await session.context_guard.check_and_compact(
            session.state, force=True
        )
        msg_count = len(session.state.messages)
        return f"✓ Context compacted. {msg_count} messages retained."
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/commands/test_handlers.py::test_compact_command -xvs`
Expected: PASS

**Step 5: Write tests for ContextCommand**

```python
def test_context_command(mock_session):
    """Test context command shows session info."""
    cmd = ContextCommand()
    result = cmd.execute("", mock_session)
    assert "**Session:**" in result
    assert "**Agent:**" in result
    assert "**Messages:**" in result
    assert "**Tokens:**" in result
```

**Step 6: Run test to verify it fails**

Run: `pytest tests/core/commands/test_handlers.py::test_context_command -xvs`
Expected: FAIL

**Step 7: Implement ContextCommand**

Add to `src/picklebot/core/commands/handlers.py`:

```python
class ContextCommand(Command):
    """Show session context information."""

    name = "context"
    description = "Show session context information"

    def execute(self, args: str, session: AgentSession) -> str:
        lines = [
            f"**Session:** `{session.session_id}`",
            f"**Agent:** {session.agent.agent_def.name}",
            f"**Source:** `{session.source}`",
            f"**Messages:** {len(session.state.messages)}",
            f"**Tokens:** {session.context_guard.estimate_tokens(session.state):,}",
        ]
        return "\n".join(lines)
```

**Step 8: Run test to verify it passes**

Run: `pytest tests/core/commands/test_handlers.py::test_context_command -xvs`
Expected: PASS

**Step 9: Write tests for ClearCommand**

```python
def test_clear_command(mock_session, mock_context):
    """Test clear command clears session cache."""
    cmd = ClearCommand()
    source_str = str(mock_session.source)

    # Setup: source has cached session
    mock_context.config.sources[source_str] = {"session_id": "test-session"}

    result = cmd.execute("", mock_session)

    assert "✓ Conversation cleared" in result
    assert source_str not in mock_context.config.sources
```

**Step 10: Run test to verify it fails**

Run: `pytest tests/core/commands/test_handlers.py::test_clear_command -xvs`
Expected: FAIL

**Step 11: Implement ClearCommand**

Add to `src/picklebot/core/commands/handlers.py`:

```python
class ClearCommand(Command):
    """Clear conversation and start fresh."""

    name = "clear"
    description = "Clear conversation and start fresh"

    def execute(self, args: str, session: AgentSession) -> str:
        # Clear session cache
        source_str = str(session.source)
        session.shared_context.routing_table.clear_session_cache(source_str)

        return "✓ Conversation cleared. Next message starts fresh."
```

**Step 12: Run test to verify it passes**

Run: `pytest tests/core/commands/test_handlers.py::test_clear_command -xvs`
Expected: PASS

**Step 13: Write tests for SessionCommand**

```python
def test_session_command(mock_session):
    """Test session command shows session details."""
    cmd = SessionCommand()
    result = cmd.execute("", mock_session)
    assert "**Session ID:**" in result
    assert "**Agent:**" in result
    assert "**Created:**" in result
    assert "**Messages:**" in result
    assert "**Source:**" in result
```

**Step 14: Run test to verify it fails**

Run: `pytest tests/core/commands/test_handlers.py::test_session_command -xvs`
Expected: FAIL

**Step 15: Implement SessionCommand**

Add to `src/picklebot/core/commands/handlers.py`:

```python
class SessionCommand(Command):
    """Show current session details."""

    name = "session"
    description = "Show current session details"

    def execute(self, args: str, session: AgentSession) -> str:
        info = session.shared_context.history_store.get_session_info(
            session.session_id
        )
        lines = [
            f"**Session ID:** `{session.session_id}`",
            f"**Agent:** {session.agent.agent_def.name} (`{session.agent.agent_def.id}`)",
            f"**Created:** {info.created_at}",
            f"**Messages:** {len(session.state.messages)}",
            f"**Source:** `{session.source}`",
        ]
        return "\n".join(lines)
```

**Step 16: Run test to verify it passes**

Run: `pytest tests/core/commands/test_handlers.py::test_session_command -xvs`
Expected: PASS

**Step 17: Commit**

```bash
git add src/picklebot/core/commands/handlers.py tests/core/commands/test_handlers.py
git commit -m "feat: add new session-aware commands (compact, context, clear, session)"
```

---

## Task 5: Update CommandRegistry.dispatch

**Files:**
- Modify: `src/picklebot/core/commands/registry.py`
- Modify: `src/picklebot/core/commands/__init__.py` (add imports)
- Modify: `tests/core/commands/test_registry.py`

**Step 1: Update tests for CommandRegistry.dispatch**

Update `tests/core/commands/test_registry.py`:

```python
def test_dispatch_with_session(mock_session, mock_context):
    """Test dispatch with AgentSession."""
    registry = CommandRegistry.with_builtins()
    mock_session.shared_context = mock_context

    result = registry.dispatch("/help", mock_session)

    assert result is not None
    assert "**Available Commands:**" in result


def test_dispatch_non_command_returns_none(mock_session):
    """Test dispatch returns None for non-command input."""
    registry = CommandRegistry()

    result = registry.dispatch("regular message", mock_session)

    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/commands/test_registry.py::test_dispatch_with_session -xvs`
Expected: FAIL with signature mismatch

**Step 3: Update CommandRegistry.dispatch signature**

Modify `src/picklebot/core/commands/registry.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picklebot.core.agent import AgentSession
    from picklebot.core.context import SharedContext


class CommandRegistry:
    """Registry for slash commands."""

    # ... existing methods ...

    def dispatch(self, input: str, session: "AgentSession") -> str | None:
        """
        Parse and execute a slash command.

        Args:
            input: Full input string
            session: AgentSession with full context

        Returns:
            Response string if command matched, None if not a command
        """
        resolved = self.resolve(input)
        if not resolved:
            return None

        cmd, args = resolved
        return cmd.execute(args, session)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/commands/test_registry.py -xvs`
Expected: PASS

**Step 5: Update CommandRegistry.with_builtins**

Update `src/picklebot/core/commands/registry.py`:

```python
@classmethod
def with_builtins(cls) -> "CommandRegistry":
    """Create registry with built-in commands registered."""
    from picklebot.core.commands.handlers import (
        HelpCommand,
        AgentCommand,
        SkillsCommand,
        CronsCommand,
        CompactCommand,
        ContextCommand,
        ClearCommand,
        SessionCommand,
    )

    registry = cls()
    registry.register(HelpCommand())
    registry.register(AgentCommand())
    registry.register(SkillsCommand())
    registry.register(CronsCommand())
    registry.register(CompactCommand())
    registry.register(ContextCommand())
    registry.register(ClearCommand())
    registry.register(SessionCommand())
    return registry
```

**Step 6: Run all command tests to verify**

Run: `pytest tests/core/commands/ -xvs`
Expected: PASS

**Step 7: Commit**

```bash
git add src/picklebot/core/commands/ tests/core/commands/
git commit -m "refactor: update CommandRegistry.dispatch to receive AgentSession"
```

---

## Task 6: Add Command Dispatch to AgentWorker

**Files:**
- Modify: `src/picklebot/server/agent_worker.py`
- Modify: `tests/server/test_agent_worker.py`

**Step 1: Write test for command dispatch in AgentWorker**

Add to `tests/server/test_agent_worker.py`:

```python
@pytest.mark.asyncio
async def test_agent_worker_dispatches_command(mock_context, mock_session):
    """Test AgentWorker dispatches slash commands before chat."""
    # Setup: agent worker with command registry
    worker = AgentWorker(mock_context)

    # Create inbound event with command
    event = InboundEvent(
        session_id="test-session",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="/help",
        timestamp=time.time(),
    )

    # Process should dispatch command and skip agent chat
    with patch.object(worker, '_emit_response') as mock_emit:
        await worker._process_event(event)

        # Verify response emitted with command result
        assert mock_emit.called
        call_args = mock_emit.call_args
        assert "**Available Commands:**" in call_args[0][1]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/server/test_agent_worker.py::test_agent_worker_dispatches_command -xvs`
Expected: FAIL (command not dispatched)

**Step 3: Implement command dispatch in AgentWorker**

Modify `src/picklebot/server/agent_worker.py`:

Find the `_process_event` method and add command dispatch after session is loaded:

```python
async def _process_event(self, event: InboundEvent):
    """Process an inbound event."""
    # Load agent and session
    agent = self.context.agent_loader.load(event.agent_id)
    session = agent.resume_or_create(event.session_id, event.source)

    # Check for slash command FIRST
    if event.content.startswith("/"):
        result = self.context.command_registry.dispatch(
            event.content, session
        )
        if result:
            # Emit response and skip agent chat
            await self._emit_response(event, result, session)
            return

    # Normal chat flow
    response = await session.chat(event.content)
    await self._emit_response(event, response, session)


async def _emit_response(
    self,
    event: InboundEvent,
    content: str,
    session: AgentSession
) -> None:
    """Emit OutboundEvent with response."""
    outbound = OutboundEvent(
        session_id=session.session_id,
        agent_id=event.agent_id,
        source=event.source,
        content=content,
        timestamp=time.time(),
    )
    await self.context.eventbus.publish(outbound)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/server/test_agent_worker.py::test_agent_worker_dispatches_command -xvs`
Expected: PASS

**Step 5: Write test that commands skip agent chat**

```python
@pytest.mark.asyncio
async def test_command_skips_agent_chat(mock_context):
    """Test that commands don't trigger agent chat."""
    worker = AgentWorker(mock_context)

    event = InboundEvent(
        session_id="test",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="/help",
        timestamp=time.time(),
    )

    with patch.object(mock_context.agent_loader.load("pickle"), 'resume_or_create') as mock_session:
        session_instance = mock_session.return_value
        session_instance.chat = AsyncMock()

        await worker._process_event(event)

        # Verify chat was NOT called
        session_instance.chat.assert_not_called()
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/server/test_agent_worker.py::test_command_skips_agent_chat -xvs`
Expected: PASS

**Step 7: Commit**

```bash
git add src/picklebot/server/agent_worker.py tests/server/test_agent_worker.py
git commit -m "feat: add command dispatch to AgentWorker before agent chat"
```

---

## Task 7: Remove Command Dispatch from ChannelWorker

**Files:**
- Modify: `src/picklebot/server/channel_worker.py`
- Modify: `tests/server/test_channel_worker.py`

**Step 1: Update tests to remove command dispatch expectations**

In `tests/server/test_channel_worker.py`, find tests that verify command dispatch and update them:

```python
@pytest.mark.asyncio
async def test_channel_worker_does_not_dispatch_commands(channel_worker, mock_channel):
    """Test that ChannelWorker no longer dispatches commands."""
    # Commands are now handled by AgentWorker
    message = "/help"
    source = CliEventSource(user_id="test")

    await channel_worker._create_callback("cli")(message, source)

    # Verify event was published (not intercepted by command dispatch)
    assert channel_worker.context.eventbus.publish.called
    event = channel_worker.context.eventbus.publish.call_args[0][0]
    assert isinstance(event, InboundEvent)
    assert event.content == "/help"  # Command not consumed
```

**Step 2: Run tests to see current state**

Run: `pytest tests/server/test_channel_worker.py -xvs`
Expected: Some tests may fail (command dispatch already removed or still present)

**Step 3: Remove command dispatch from ChannelWorker**

In `src/picklebot/server/channel_worker.py`, find and remove the command dispatch block:

```python
# REMOVE THIS BLOCK:
# Check for slash command
if message.startswith("/"):
    self.logger.debug(f"Processing slash command from {platform}")
    result = self.context.command_registry.dispatch(
        message, self.context
    )
    if result:
        return await channel.reply(result, source)
```

The callback should now directly create and publish InboundEvent for all messages.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/server/test_channel_worker.py -xvs`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/server/channel_worker.py tests/server/test_channel_worker.py
git commit -m "refactor: remove command dispatch from ChannelWorker"
```

---

## Task 8: Update Integration Tests

**Files:**
- Modify: `tests/integration/test_command_flow.py` (create if needed)

**Step 1: Write end-to-end test for command flow**

Create `tests/integration/test_command_flow.py`:

```python
"""End-to-end tests for command dispatch flow."""
import pytest
from picklebot.core.events import InboundEvent, CliEventSource
from picklebot.server.agent_worker import AgentWorker


@pytest.mark.asyncio
async def test_agent_switch_command_flow(test_context):
    """Test /agent command switches agent and starts fresh session."""
    # Setup worker
    worker = AgentWorker(test_context)

    # Message 1: Start with pickle
    event1 = InboundEvent(
        session_id="session-1",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="Hello from user",
        timestamp=1000.0,
    )
    await worker._process_event(event1)

    # Message 2: Switch to cookie
    event2 = InboundEvent(
        session_id="session-1",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="/agent cookie",
        timestamp=1001.0,
    )
    await worker._process_event(event2)

    # Verify routing updated
    source_str = "platform-cli:test"
    resolved_agent = test_context.routing_table.resolve(source_str)
    assert resolved_agent == "cookie"

    # Verify session cache cleared
    assert source_str not in test_context.config.sources


@pytest.mark.asyncio
async def test_clear_command_flow(test_context):
    """Test /clear command clears conversation."""
    worker = AgentWorker(test_context)

    # Message 1: Some conversation
    event1 = InboundEvent(
        session_id="session-1",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="Hello",
        timestamp=1000.0,
    )
    await worker._process_event(event1)

    # Add session to cache
    source_str = "platform-cli:test"
    test_context.config.sources[source_str] = {"session_id": "session-1"}

    # Message 2: Clear command
    event2 = InboundEvent(
        session_id="session-1",
        agent_id="pickle",
        source=CliEventSource(user_id="test"),
        content="/clear",
        timestamp=1001.0,
    )
    await worker._process_event(event2)

    # Verify cache cleared
    assert source_str not in test_context.config.sources
```

**Step 2: Run integration tests**

Run: `pytest tests/integration/test_command_flow.py -xvs`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_command_flow.py
git commit -m "test: add integration tests for command dispatch flow"
```

---

## Task 9: Fix Async Command Execution

**Files:**
- Modify: `src/picklebot/core/commands/base.py`
- Modify: `src/picklebot/core/commands/registry.py`
- Modify: `src/picklebot/server/agent_worker.py`

**Step 1: Update Command base class for async**

Modify `src/picklebot/core/commands/base.py`:

```python
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picklebot.core.agent import AgentSession


class Command(ABC):
    """Base class for slash commands."""

    name: str
    aliases: list[str] = []
    description: str = ""

    @abstractmethod
    async def execute(self, args: str, session: "AgentSession") -> str:
        """Execute the command and return response string."""
        pass
```

**Step 2: Update CommandRegistry.dispatch for async**

Modify `src/picklebot/core/commands/registry.py`:

```python
async def dispatch(self, input: str, session: "AgentSession") -> str | None:
    """
    Parse and execute a slash command.

    Args:
        input: Full input string
        session: AgentSession with full context

    Returns:
        Response string if command matched, None if not a command
    """
    resolved = self.resolve(input)
    if not resolved:
        return None

    cmd, args = resolved
    return await cmd.execute(args, session)
```

**Step 3: Update AgentWorker for async dispatch**

Modify `src/picklebot/server/agent_worker.py`:

```python
# Check for slash command FIRST
if event.content.startswith("/"):
    result = await self.context.command_registry.dispatch(
        event.content, session
    )
    if result:
        # Emit response and skip agent chat
        await self._emit_response(event, result, session)
        return
```

**Step 4: Update all commands to async**

Update all command `execute` methods to be `async def`:

```python
async def execute(self, args: str, session: AgentSession) -> str:
    # ... implementation ...
```

**Step 5: Run all tests**

Run: `pytest tests/core/commands/ tests/server/test_agent_worker.py -xvs`
Expected: PASS

**Step 6: Commit**

```bash
git add src/picklebot/core/commands/ src/picklebot/server/agent_worker.py tests/
git commit -m "refactor: make command execution async"
```

---

## Task 10: Update Documentation

**Files:**
- Modify: `docs/features.md`
- Modify: `README.md` (if needed)

**Step 1: Update features.md with new commands**

Add section to `docs/features.md`:

```markdown
## Slash Commands

Commands for managing conversations and agents. All commands start with `/`.

**Available Commands:**

| Command | Description |
|---------|-------------|
| `/help` or `/?` | Show available commands |
| `/agent [<id>]` | List agents or switch to different agent |
| `/skills` | List all skills |
| `/crons` | List all cron jobs |
| `/compact` | Trigger manual context compaction |
| `/context` | Show session context information |
| `/clear` | Clear conversation and start fresh |
| `/session` | Show current session details |

**Examples:**

```bash
# Switch to cookie agent
/agent cookie

# Check session info
/context

# Clear conversation
/clear
```

**Agent Switching:**

The `/agent <id>` command updates routing for your channel and starts a fresh conversation with the new agent. Previous conversation history is preserved in the old session.
```

**Step 2: Commit**

```bash
git add docs/features.md
git commit -m "docs: update features with new slash commands"
```

---

## Task 11: Final Verification

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Run linting and formatting**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 3: Test manually with CLI**

Run: `uv run picklebot chat`
Test commands:
- `/help`
- `/agent`
- `/agent cookie`
- `/context`
- `/session`
- `/clear`

**Step 4: Final commit (if needed)**

```bash
git add .
git commit -m "chore: final cleanup for session-aware commands"
```

---

## Summary

**Commands Implemented:**
- `/help` - Show available commands
- `/agent [<id>]` - List agents or switch agent
- `/skills` - List skills
- `/crons` - List cron jobs
- `/compact` - Manual context compaction
- `/context` - Show session context
- `/clear` - Clear conversation
- `/session` - Show session details

**Architecture Changes:**
- Command dispatch moved from ChannelWorker to AgentWorker
- Commands receive AgentSession instead of SharedContext
- Two new RoutingTable methods: `add_runtime_binding()`, `clear_session_cache()`
- All command execution is now async

**Testing:**
- Unit tests for all new methods and commands
- Integration tests for command flow
- Manual CLI testing guide included
