# Session State Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix session rolling bug by introducing SessionState as a swappable data container.

**Architecture:** Extract message storage and persistence from AgentSession into a new SessionState class. ContextGuard returns new SessionState on roll, AgentSession swaps the reference.

**Tech Stack:** Python dataclasses, asyncio, litellm, pydantic

---

## Task 1: Create SessionState class

**Files:**
- Create: `src/picklebot/core/session_state.py`
- Test: `tests/core/test_session_state.py`

**Step 1: Write the failing test for SessionState creation**

```python
# tests/core/test_session_state.py
"""Tests for SessionState class."""

import pytest
from unittest.mock import MagicMock

from picklebot.core.session_state import SessionState
from picklebot.core.events import TelegramEventSource
from picklebot.core.history import HistoryMessage


class TestSessionStateCreation:
    def test_session_state_creation(self, tmp_path):
        """SessionState can be created with required fields."""
        from picklebot.core.history import HistoryStore

        mock_agent = MagicMock()
        mock_agent.agent_def.id = "test-agent"

        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="test-session-id",
            agent=mock_agent,
            messages=[],
            source=source,
            shared_context=mock_context,
        )

        assert state.session_id == "test-session-id"
        assert state.agent is mock_agent
        assert state.messages == []
        assert state.source == source
        assert state.shared_context is mock_context
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_session_state.py -v`
Expected: FAIL with "No module named 'picklebot.core.session_state'"

**Step 3: Write minimal SessionState implementation**

```python
# src/picklebot/core/session_state.py
"""Session state container with persistence helpers."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from litellm.types.completion import ChatCompletionMessageParam as Message

from picklebot.core.history import HistoryMessage

if TYPE_CHECKING:
    from picklebot.core.agent import Agent
    from picklebot.core.context import SharedContext
    from picklebot.core.events import EventSource


@dataclass
class SessionState:
    """Pure conversation state + persistence."""

    session_id: str
    agent: "Agent"
    messages: list[Message]
    source: "EventSource"
    shared_context: "SharedContext"

    def add_message(self, message: Message) -> None:
        """Add message to in-memory list + persist."""
        self.messages.append(message)
        self._persist_message(message)

    def get_history(self) -> list[Message]:
        """Get all messages for LLM context."""
        return self.messages

    def _persist_message(self, message: Message) -> None:
        """Save to HistoryStore."""
        history_msg = HistoryMessage.from_message(message)
        self.shared_context.history_store.save_message(self.session_id, history_msg)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_session_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/session_state.py tests/core/test_session_state.py
git commit -m "feat: add SessionState class for swappable session data"
```

---

## Task 2: Add SessionState persistence tests

**Files:**
- Modify: `tests/core/test_session_state.py`

**Step 1: Write the failing test for add_message persistence**

```python
# Add to tests/core/test_session_state.py

class TestSessionStatePersistence:
    def test_add_message_persists_to_history(self, tmp_path):
        """add_message should persist to HistoryStore."""
        from picklebot.core.history import HistoryStore

        mock_agent = MagicMock()
        mock_agent.agent_def.id = "test-agent"

        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="test-session-id",
            agent=mock_agent,
            messages=[],
            source=source,
            shared_context=mock_context,
        )

        # Create session in history store
        mock_context.history_store.create_session("test-agent", "test-session-id", source)

        # Add a message
        state.add_message({"role": "user", "content": "Hello"})

        # Verify persisted
        messages = mock_context.history_store.get_messages("test-session-id")
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"

    def test_add_message_appends_to_memory(self, tmp_path):
        """add_message should append to in-memory list."""
        from picklebot.core.history import HistoryStore

        mock_agent = MagicMock()
        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="test-session-id",
            agent=mock_agent,
            messages=[],
            source=source,
            shared_context=mock_context,
        )

        mock_context.history_store.create_session("test-agent", "test-session-id", source)

        state.add_message({"role": "user", "content": "Hello"})
        state.add_message({"role": "assistant", "content": "Hi"})

        assert len(state.messages) == 2
        assert state.messages[0]["content"] == "Hello"
        assert state.messages[1]["content"] == "Hi"

    def test_get_history_returns_messages(self, tmp_path):
        """get_history should return the messages list."""
        from picklebot.core.history import HistoryStore

        mock_agent = MagicMock()
        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="test-session-id",
            agent=mock_agent,
            messages=[{"role": "user", "content": "Test"}],
            source=source,
            shared_context=mock_context,
        )

        history = state.get_history()
        assert len(history) == 1
        assert history[0]["content"] == "Test"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_session_state.py -v`
Expected: PASS (implementation already supports this)

**Step 3: Commit**

```bash
git add tests/core/test_session_state.py
git commit -m "test: add SessionState persistence tests"
```

---

## Task 3: Update ContextGuard to work with SessionState

**Files:**
- Modify: `src/picklebot/core/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test for new check_and_compact signature**

```python
# Add to tests/test_context_guard.py

class TestCheckAndCompactWithSessionState:
    @pytest.mark.asyncio
    async def test_check_and_compact_returns_tuple(self):
        """check_and_compact should return (messages, new_state | None) tuple."""
        from picklebot.core.session_state import SessionState

        mock_context = MagicMock()
        guard = ContextGuard(shared_context=mock_context, token_threshold=10000)

        mock_agent = MagicMock()
        mock_agent.llm.model = "gpt-4"

        mock_shared = MagicMock()

        state = SessionState(
            session_id="test-id",
            agent=mock_agent,
            messages=[{"role": "user", "content": "Hello"}],
            source=TelegramEventSource(user_id="123", chat_id="456"),
            shared_context=mock_shared,
        )

        # Mock _build_full_messages to return the messages
        with patch.object(guard, '_build_full_messages', return_value=[{"role": "user", "content": "Hello"}]):
            messages, new_state = await guard.check_and_compact(state)

        # Under threshold, should return original messages, no new state
        assert messages is not None
        assert new_state is None

    @pytest.mark.asyncio
    async def test_check_and_compact_returns_new_state_on_roll(self, tmp_path):
        """check_and_compact should return new SessionState when rolling."""
        from picklebot.core.session_state import SessionState
        from picklebot.core.history import HistoryStore

        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)
        mock_context.config.set_runtime = MagicMock()
        mock_context.prompt_builder = MagicMock()
        mock_context.prompt_builder.build.return_value = "System prompt"

        guard = ContextGuard(shared_context=mock_context, token_threshold=10)

        mock_agent = MagicMock()
        mock_agent.llm.model = "gpt-4"
        mock_agent.agent_def.id = "test-agent"

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="old-session-id",
            agent=mock_agent,
            messages=[{"role": "user", "content": f"Message {i} " * 100} for i in range(20)],
            source=source,
            shared_context=mock_context,
        )

        # Create old session in history
        mock_context.history_store.create_session("test-agent", "old-session-id", source)

        with patch.object(guard, "_generate_summary", new_callable=AsyncMock, return_value="Summary"):
            messages, new_state = await guard.check_and_compact(state)

        # Should return new state
        assert new_state is not None
        assert new_state.session_id != "old-session-id"
        assert new_state.messages == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestCheckAndCompactWithSessionState -v`
Expected: FAIL (signature mismatch)

**Step 3: Update ContextGuard implementation**

```python
# src/picklebot/core/context_guard.py
"""Context guard for proactive context window management."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from litellm import token_counter
from litellm.types.completion import ChatCompletionMessageParam as Message, ChatCompletionAssistantMessageParam

if TYPE_CHECKING:
    from picklebot.core.session_state import SessionState
    from picklebot.core.context import SharedContext


@dataclass
class ContextGuard:
    """Manages context window size with proactive compaction."""

    shared_context: "SharedContext"
    token_threshold: int = 160000  # 80% of 200k context

    def count_tokens(self, messages: list[Message], model: str) -> int:
        """Count tokens using litellm's token_counter."""
        if not messages:
            return 0
        return token_counter(model=model, messages=messages)

    def _serialize_messages_for_summary(self, messages: list[Message]) -> str:
        """Serialize messages to plain text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "assistant" and msg.get("tool_calls"):
                tool_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in (cast(ChatCompletionAssistantMessageParam, msg)).get("tool_calls", [])
                ]
                lines.append(
                    f"ASSISTANT: [used tools: {', '.join(tool_names)}] {content}"
                )
            else:
                lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)

    def _build_compacted_messages(
        self,
        summary: str,
        original_messages: list[Message],
    ) -> list[Message]:
        """Build new message list with summary + recent messages."""
        keep_count = max(4, int(len(original_messages) * 0.2))
        compress_count = max(2, int(len(original_messages) * 0.5))
        compress_count = min(compress_count, len(original_messages) - keep_count)

        messages: list[Message] = []
        messages.append(
            {
                "role": "user",
                "content": f"[Previous conversation summary]\n{summary}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Understood, I have the context.",
            }
        )
        messages.extend(original_messages[compress_count:])
        return messages

    def _build_full_messages(self, state: "SessionState") -> list[Message]:
        """Build full message list with system prompt."""
        system_prompt = state.shared_context.prompt_builder.build_for_state(state)
        messages: list[Message] = [{"role": "system", "content": system_prompt}]
        messages.extend(state.get_history())
        return messages

    async def check_and_compact(
        self,
        state: "SessionState",
    ) -> tuple[list[Message], "SessionState | None"]:
        """Check token count, compact and roll if needed.

        Args:
            state: Current session state

        Returns:
            - (compacted_messages, new_state) if rolled
            - (original_messages, None) if no roll
        """
        messages = self._build_full_messages(state)
        token_count = self.count_tokens(messages, state.agent.llm.model)

        if token_count < self.token_threshold:
            return messages, None

        return await self._compact_and_roll(state, messages)

    async def _compact_and_roll(
        self,
        state: "SessionState",
        messages: list[Message],
    ) -> tuple[list[Message], "SessionState"]:
        """Compact history, roll to new session, return compacted messages + new state."""
        summary = await self._generate_summary(state, messages)
        new_state = self._roll_session(state)
        compacted_messages = self._build_compacted_messages(summary, messages)
        return compacted_messages, new_state

    def _roll_session(self, state: "SessionState") -> "SessionState":
        """Create new SessionState, update source mapping."""
        from picklebot.core.session_state import SessionState

        new_session_id = str(uuid.uuid4())

        # Create new session in HistoryStore
        state.shared_context.history_store.create_session(
            state.agent.agent_def.id,
            new_session_id,
            state.source,
        )

        # Update source -> session mapping
        state.shared_context.config.set_runtime(
            f"sources.{state.source}",
            {"session_id": new_session_id},
        )

        # Return new SessionState
        return SessionState(
            session_id=new_session_id,
            agent=state.agent,
            messages=[],
            source=state.source,
            shared_context=state.shared_context,
        )

    async def _generate_summary(
        self,
        state: "SessionState",
        messages: list[Message],
    ) -> str:
        """Generate summary of older messages using agent's LLM."""
        keep_count = max(4, int(len(messages) * 0.2))
        compress_count = max(2, int(len(messages) * 0.5))
        compress_count = min(compress_count, len(messages) - keep_count)

        old_messages = messages[:compress_count]
        old_text = self._serialize_messages_for_summary(old_messages)

        summary_prompt = f"""Summarize the conversation so far. Keep it factual and concise. Focus on key decisions, facts, and user preferences discovered:

{old_text}"""

        response, _ = await state.agent.llm.chat(
            [{"role": "user", "content": summary_prompt}],
            [],
        )
        return response
```

**Step 4: Add PromptBuilder.build_for_state method**

First add a test:

```python
# Add to tests/core/test_prompt_builder.py or create new test

def test_build_for_state_with_session_state(tmp_path, test_config):
    """PromptBuilder.build_for_state should work with SessionState."""
    from picklebot.core.session_state import SessionState
    from picklebot.core.prompt_builder import PromptBuilder
    from picklebot.core.context import SharedContext
    from picklebot.core.agent_loader import AgentDef
    from picklebot.core.events import TelegramEventSource

    context = SharedContext(config=test_config)
    builder = PromptBuilder(context)

    mock_agent = MagicMock()
    mock_agent.agent_def = AgentDef(
        id="test-agent",
        name="Test Agent",
        agent_md="You are a test assistant.",
        llm=test_config.default_llm,
    )

    state = SessionState(
        session_id="test-id",
        agent=mock_agent,
        messages=[],
        source=TelegramEventSource(user_id="123", chat_id="456"),
        shared_context=context,
    )

    prompt = builder.build_for_state(state)
    assert "You are a test assistant." in prompt
    assert "telegram" in prompt.lower()
```

Then add the method to PromptBuilder:

```python
# Add to src/picklebot/core/prompt_builder.py

def build_for_state(self, state: "SessionState") -> str:
    """Build the full system prompt from layers using SessionState.

    Args:
        state: SessionState with agent and source

    Returns:
        Assembled system prompt string
    """
    layers = []

    # Layer 1: Identity
    layers.append(state.agent.agent_def.agent_md)

    # Layer 2: Soul (optional)
    if state.agent.agent_def.soul_md:
        layers.append(f"## Personality\n\n{state.agent.agent_def.soul_md}")

    # Layer 3: Bootstrap context
    bootstrap = self._load_bootstrap_context()
    if bootstrap:
        layers.append(bootstrap)

    # Layer 4: Runtime context
    layers.append(
        self._build_runtime_context(
            state.agent.agent_def.id,
            datetime.now(),
        )
    )

    # Layer 5: Channel hint
    layers.append(self._build_channel_hint(state.source))

    return "\n\n".join(layers)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_context_guard.py::TestCheckAndCompactWithSessionState -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/picklebot/core/context_guard.py src/picklebot/core/prompt_builder.py tests/
git commit -m "refactor: update ContextGuard to work with SessionState"
```

---

## Task 4: Update AgentSession to use SessionState

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Modify: `tests/core/test_agent.py`

**Step 1: Write the failing test for AgentSession with SessionState**

```python
# Add to tests/core/test_agent.py

class TestAgentSessionWithSessionState:
    def test_agent_session_has_state(self, test_agent):
        """AgentSession should have a state field."""
        source = TelegramEventSource(user_id="123", chat_id="456")
        session = test_agent.new_session(source=source)

        assert hasattr(session, 'state')
        assert session.state.session_id == session.session_id

    def test_agent_session_state_is_swappable(self, test_agent):
        """AgentSession.state should be swappable."""
        from picklebot.core.session_state import SessionState

        source = TelegramEventSource(user_id="123", chat_id="456")
        session = test_agent.new_session(source=source)

        old_state = session.state
        new_state = SessionState(
            session_id="new-session-id",
            agent=test_agent,
            messages=[],
            source=source,
            shared_context=test_agent.context,
        )

        session.state = new_state

        assert session.state.session_id == "new-session-id"
        assert session.state is not old_state
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_agent.py::TestAgentSessionWithSessionState -v`
Expected: FAIL (no state field)

**Step 3: Update AgentSession implementation**

```python
# Update src/picklebot/core/agent.py

# Add import at top:
from picklebot.core.session_state import SessionState

# Update AgentSession class:
@dataclass
class AgentSession:
    """Chat orchestrator - operates on swappable SessionState."""

    agent: Agent
    state: SessionState  # Swappable reference
    context_guard: ContextGuard
    tools: ToolRegistry

    @property
    def session_id(self) -> str:
        """Get session ID from state."""
        return self.state.session_id

    @property
    def source(self) -> "EventSource":
        """Get source from state."""
        return self.state.source

    @property
    def shared_context(self) -> "SharedContext":
        """Get shared context from state."""
        return self.state.shared_context

    async def chat(self, message: str) -> str:
        """Send message to LLM and get response."""
        user_msg: Message = {"role": "user", "content": message}
        self.state.add_message(user_msg)

        tool_schemas = self.tools.get_tool_schemas()

        while True:
            messages = self._build_messages()

            # Check context and compact if needed (may swap state)
            messages, new_state = await self.context_guard.check_and_compact(self.state)
            if new_state:
                self.state = new_state  # Swap to new session!

            content, tool_calls = await self.agent.llm.chat(messages, tool_schemas)

            tool_call_dicts: list[ChatCompletionMessageToolCallParam] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in tool_calls
            ]
            assistant_msg: Message = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_call_dicts,
            }

            self.state.add_message(assistant_msg)

            if not tool_calls:
                break

            await self._handle_tool_calls(tool_calls)

            continue

        return content

    def _build_messages(self) -> list[Message]:
        """Build messages for LLM API call."""
        system_prompt = self.state.shared_context.prompt_builder.build_for_state(self.state)
        messages: list[Message] = [{"role": "system", "content": system_prompt}]
        messages.extend(self.state.get_history())
        return messages

    async def _handle_tool_calls(
        self,
        tool_calls: list["LLMToolCall"],
    ) -> None:
        """Handle tool calls from LLM response."""
        tool_call_results = await asyncio.gather(
            *[self._execute_tool_call(tool_call) for tool_call in tool_calls]
        )

        for tool_call, result in zip(tool_calls, tool_call_results):
            tool_msg: Message = {
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call.id,
            }
            self.state.add_message(tool_msg)

    async def _execute_tool_call(
        self,
        tool_call: "LLMToolCall",
    ) -> str:
        """Execute a single tool call."""
        try:
            args = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            args = {}

        try:
            result = await self.tools.execute_tool(tool_call.name, session=self, **args)
        except Exception as e:
            result = f"Error executing tool: {e}"

        return result
```

**Step 4: Update Agent.new_session to create SessionState**

```python
# Update Agent.new_session in src/picklebot/core/agent.py

def new_session(
    self,
    source: "EventSource",
    session_id: str | None = None,
) -> "AgentSession":
    """Create a new conversation session."""
    session_id = session_id or str(uuid.uuid4())

    # Build tools for this session
    include_post_message = source.is_cron
    tools = self._build_tools(include_post_message)

    # Create SessionState
    state = SessionState(
        session_id=session_id,
        agent=self,
        messages=[],
        source=source,
        shared_context=self.context,
    )

    # Persist session
    self.context.history_store.create_session(self.agent_def.id, session_id, source)

    # Create context guard
    context_guard = ContextGuard(
        shared_context=self.context,
        token_threshold=self._get_token_threshold(),
    )

    return AgentSession(
        agent=self,
        state=state,
        context_guard=context_guard,
        tools=tools,
    )
```

**Step 5: Update Agent.resume_session to create SessionState**

```python
# Update Agent.resume_session in src/picklebot/core/agent.py

def resume_session(self, session_id: str) -> "AgentSession":
    """Load an existing conversation session."""
    session_query = [
        session
        for session in self.context.history_store.list_sessions()
        if session.id == session_id
    ]
    if not session_query:
        raise ValueError(f"Session not found: {session_id}")

    session_info = session_query[0]

    # Get typed EventSource from stored string
    source = session_info.get_source()
    include_post_message = source.is_cron

    # Get all messages
    history_messages = self.context.history_store.get_messages(session_id)
    messages: list[Message] = [msg.to_message() for msg in history_messages]

    # Build tools for resumed session
    tools = self._build_tools(include_post_message)

    # Reconstruct SessionState
    state = SessionState(
        session_id=session_info.id,
        agent=self,
        messages=messages,
        source=source,
        shared_context=self.context,
    )

    # Create context guard
    context_guard = ContextGuard(
        shared_context=self.context,
        token_threshold=self._get_token_threshold(),
    )

    return AgentSession(
        agent=self,
        state=state,
        context_guard=context_guard,
        tools=tools,
    )
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_agent.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/picklebot/core/agent.py tests/core/test_agent.py
git commit -m "refactor: update AgentSession to use swappable SessionState"
```

---

## Task 5: Update existing tests for compatibility

**Files:**
- Modify: `tests/test_context_guard.py`
- Modify: Various test files that reference old AgentSession fields

**Step 1: Update TestCheckAndCompact tests**

Remove or update the old tests that use the old signature:

```python
# Update tests/test_context_guard.py

class TestCheckAndCompact:
    @pytest.mark.asyncio
    async def test_check_and_compact_under_threshold(self):
        """Returns messages unchanged when under threshold."""
        from picklebot.core.session_state import SessionState

        mock_context = MagicMock()
        mock_context.prompt_builder = MagicMock()
        mock_context.prompt_builder.build_for_state.return_value = "System"

        guard = ContextGuard(shared_context=mock_context, token_threshold=10000)

        mock_agent = MagicMock()
        mock_agent.llm.model = "gpt-4"

        state = SessionState(
            session_id="test-id",
            agent=mock_agent,
            messages=[{"role": "user", "content": "Hello"}],
            source=TelegramEventSource(user_id="123", chat_id="456"),
            shared_context=mock_context,
        )

        messages, new_state = await guard.check_and_compact(state)

        # Should return same messages (under threshold), no new state
        assert messages is not None
        assert new_state is None

    @pytest.mark.asyncio
    async def test_check_and_compact_over_threshold_triggers_compaction(self, tmp_path):
        """Triggers compaction when over threshold."""
        from picklebot.core.session_state import SessionState
        from picklebot.core.history import HistoryStore

        mock_context = MagicMock()
        mock_context.history_store = HistoryStore(tmp_path)
        mock_context.config.set_runtime = MagicMock()
        mock_context.prompt_builder = MagicMock()
        mock_context.prompt_builder.build_for_state.return_value = "System"

        guard = ContextGuard(
            shared_context=mock_context, token_threshold=10
        )

        mock_agent = MagicMock()
        mock_agent.llm.model = "gpt-4"
        mock_agent.agent_def.id = "test-agent"

        source = TelegramEventSource(user_id="123", chat_id="456")

        state = SessionState(
            session_id="test-session-id",
            agent=mock_agent,
            messages=[{"role": "user", "content": f"Message {i} " * 100} for i in range(20)],
            source=source,
            shared_context=mock_context,
        )

        # Create session in history
        mock_context.history_store.create_session("test-agent", "test-session-id", source)

        with patch.object(
            guard, "_generate_summary", new_callable=AsyncMock, return_value="Summary"
        ):
            messages, new_state = await guard.check_and_compact(state)

        # Should return compacted messages and new state
        assert len(messages) < 20 + 1  # +1 for system prompt
        assert messages[1]["role"] == "user"  # After system prompt
        assert "[Previous conversation summary]" in messages[1]["content"]
        assert new_state is not None
```

**Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: update tests for SessionState refactoring"
```

---

## Task 6: Add integration test for session rolling

**Files:**
- Modify: `tests/core/test_agent.py`

**Step 1: Write integration test for session rolling**

```python
# Add to tests/core/test_agent.py

class TestSessionRollingIntegration:
    """Integration tests for session rolling with SessionState."""

    @pytest.mark.asyncio
    async def test_messages_go_to_new_session_after_roll(self, test_agent, tmp_path):
        """After rolling, new messages should go to the new session."""
        from unittest.mock import AsyncMock, patch

        source = TelegramEventSource(user_id="123", chat_id="456")
        session = test_agent.new_session(source=source)

        old_session_id = session.session_id

        # Mock LLM to return response
        with patch.object(
            test_agent.llm,
            'chat',
            new_callable=AsyncMock,
            return_value=("Response", [])
        ):
            # Mock check_and_compact to trigger a roll
            from picklebot.core.session_state import SessionState

            new_state = SessionState(
                session_id="new-rolled-session",
                agent=test_agent,
                messages=[],
                source=source,
                shared_context=test_agent.context,
            )

            # Create the new session in history
            test_agent.context.history_store.create_session(
                test_agent.agent_def.id,
                "new-rolled-session",
                source
            )

            with patch.object(
                session.context_guard,
                'check_and_compact',
                new_callable=AsyncMock,
                return_value=([{"role": "system", "content": "prompt"}], new_state)
            ):
                await session.chat("Hello")

        # State should be swapped
        assert session.state.session_id == "new-rolled-session"
        assert session.state.session_id != old_session_id

        # Assistant message should be in NEW session
        new_session_messages = test_agent.context.history_store.get_messages("new-rolled-session")
        assert len(new_session_messages) == 1
        assert new_session_messages[0].role == "assistant"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/core/test_agent.py::TestSessionRollingIntegration -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/core/test_agent.py
git commit -m "test: add integration test for session rolling"
```

---

## Task 7: Run full test suite and fix any issues

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v`

**Step 2: Fix any failing tests**

Address any test failures by updating test code or implementation as needed.

**Step 3: Run linter and formatter**

Run: `uv run black . && uv run ruff check .`

**Step 4: Final commit if any fixes were made**

```bash
git add .
git commit -m "fix: address test failures after SessionState refactoring"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Create SessionState class | `core/session_state.py` (new) |
| 2 | Add SessionState tests | `tests/core/test_session_state.py` |
| 3 | Update ContextGuard | `core/context_guard.py`, `core/prompt_builder.py` |
| 4 | Update AgentSession | `core/agent.py` |
| 5 | Update existing tests | Various test files |
| 6 | Add integration test | `tests/core/test_agent.py` |
| 7 | Full test run & fixes | All files |
