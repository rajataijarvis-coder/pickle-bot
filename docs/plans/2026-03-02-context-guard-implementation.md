# Context Guard with Session Rolling - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace message-count-based history limiting with token-aware context management that proactively compacts and rolls to new sessions.

**Architecture:** ContextGuard checks token count before each LLM call. When approaching threshold, it generates a summary of older messages using the agent's LLM, creates a new session, updates the source-to-session mapping, and returns compacted messages.

**Tech Stack:** LiteLLM token_counter, existing HistoryStore, existing event system

---

## Task 1: Create ContextGuard class skeleton

**Files:**
- Create: `src/picklebot/core/context_guard.py`
- Create: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# tests/test_context_guard.py
"""Tests for ContextGuard."""

import pytest
from picklebot.core.context_guard import ContextGuard


class TestContextGuard:
    def test_context_guard_exists(self):
        """ContextGuard can be instantiated."""
        guard = ContextGuard(token_threshold=1000)
        assert guard.token_threshold == 1000
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py -v`
Expected: FAIL with "cannot import name 'ContextGuard'"

**Step 3: Write minimal implementation**

```python
# src/picklebot/core/context_guard.py
"""Context guard for proactive context window management."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picklebot.core.context import SharedContext


@dataclass
class ContextGuard:
    """Manages context window size with proactive compaction."""

    shared_context: "SharedContext"
    token_threshold: int = 160000  # 80% of 200k context
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: add ContextGuard class skeleton"
```

---

## Task 2: Implement token counting

**Files:**
- Modify: `src/picklebot/core/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_context_guard.py

class TestTokenCounting:
    def test_count_tokens_empty_messages(self):
        """Count tokens returns 0 for empty messages."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=1000)
        count = guard.count_tokens([], "gpt-4")
        assert count == 0

    def test_count_tokens_with_messages(self):
        """Count tokens returns positive count for messages."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=1000)
        messages = [{"role": "user", "content": "Hello, world!"}]
        count = guard.count_tokens(messages, "gpt-4")
        assert count > 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestTokenCounting -v`
Expected: FAIL with "attribute 'count_tokens' not found"

**Step 3: Write minimal implementation**

```python
# Add to src/picklebot/core/context_guard.py

from litellm import token_counter
from litellm.types.completion import ChatCompletionMessageParam as Message


@dataclass
class ContextGuard:
    """Manages context window size with proactive compaction."""

    shared_context: "SharedContext"
    token_threshold: int = 160000  # 80% of 200k context

    def count_tokens(self, messages: list[Message], model: str) -> int:
        """Count tokens using litellm's token_counter.

        Args:
            messages: List of messages to count
            model: Model name for tokenizer selection

        Returns:
            Token count
        """
        if not messages:
            return 0
        return token_counter(model=model, messages=messages)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py::TestTokenCounting -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: implement token counting in ContextGuard"
```

---

## Task 3: Implement message serialization for summary

**Files:**
- Modify: `src/picklebot/core/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_context_guard.py

class TestMessageSerialization:
    def test_serialize_messages_for_summary(self):
        """Serialize messages to plain text for summarization."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=1000)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = guard._serialize_messages_for_summary(messages)

        assert "USER:" in result
        assert "Hello" in result
        assert "ASSISTANT:" in result
        assert "Hi there!" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestMessageSerialization -v`
Expected: FAIL with "attribute '_serialize_messages_for_summary' not found"

**Step 3: Write minimal implementation**

```python
# Add to ContextGuard class in src/picklebot/core/context_guard.py

    def _serialize_messages_for_summary(self, messages: list[Message]) -> str:
        """Serialize messages to plain text for summarization.

        Args:
            messages: List of messages to serialize

        Returns:
            Plain text representation
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Handle tool calls in assistant messages
            if role == "assistant" and msg.get("tool_calls"):
                tool_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in msg["tool_calls"]
                ]
                lines.append(f"ASSISTANT: [used tools: {', '.join(tool_names)}] {content}")
            else:
                lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py::TestMessageSerialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: add message serialization for summary"
```

---

## Task 4: Implement compacted messages builder

**Files:**
- Modify: `src/picklebot/core/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_context_guard.py

class TestCompactedMessagesBuilder:
    def test_build_compacted_messages(self):
        """Build compacted message list with summary + recent messages."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=1000)

        # 10 messages
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]

        summary = "This is a summary of the conversation."
        result = guard._build_compacted_messages(summary, messages)

        # Should have: summary user + summary assistant + kept recent messages
        assert result[0]["role"] == "user"
        assert "[Previous conversation summary]" in result[0]["content"]
        assert summary in result[0]["content"]

        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Understood, I have the context."

        # Recent messages should be preserved
        assert len(result) > 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestCompactedMessagesBuilder -v`
Expected: FAIL with "attribute '_build_compacted_messages' not found"

**Step 3: Write minimal implementation**

```python
# Add to ContextGuard class in src/picklebot/core/context_guard.py

    def _build_compacted_messages(
        self,
        summary: str,
        original_messages: list[Message],
    ) -> list[Message]:
        """Build new message list with summary + recent messages.

        Args:
            summary: Generated summary text
            original_messages: Original message list

        Returns:
            Compacted message list
        """
        keep_count = max(4, int(len(original_messages) * 0.2))
        compress_count = max(2, int(len(original_messages) * 0.5))
        compress_count = min(compress_count, len(original_messages) - keep_count)

        return [
            {
                "role": "user",
                "content": f"[Previous conversation summary]\n{summary}",
            },
            {
                "role": "assistant",
                "content": "Understood, I have the context.",
            },
        ] + original_messages[compress_count:]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py::TestCompactedMessagesBuilder -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: add compacted messages builder"
```

---

## Task 5: Remove chunking from HistoryStore

**Files:**
- Modify: `src/picklebot/core/history.py`
- Modify: `tests/test_history.py` (if exists)

**Step 1: Write the failing test**

Check existing tests first:
Run: `uv run pytest tests/ -k history -v`

**Step 2: Simplify HistorySession model**

```python
# Modify src/picklebot/core/history.py - HistorySession class

class HistorySession(BaseModel):
    """Session metadata - stored in index.jsonl."""

    id: str
    agent_id: str
    source: str  # Serialized EventSource (e.g., "platform-telegram:123:456")
    # REMOVED: chunk_count: int = 1
    title: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str

    # ... rest unchanged
```

**Step 3: Simplify HistoryStore methods**

```python
# Modify src/picklebot/core/history.py - HistoryStore class

class HistoryStore:
    """
    JSONL file-based history storage.

    Directory structure:
    ~/.pickle-bot/history/
    ├── index.jsonl              # Session metadata (append-only)
    └── sessions/
        └── {session_id}.jsonl   # Messages (append-only, one file per session)
    """

    @staticmethod
    def from_config(config: "Config") -> "HistoryStore":
        return HistoryStore(config.history_path)

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.sessions_path = self.base_path / "sessions"
        self.index_path = self.base_path / "index.jsonl"

        self.base_path.mkdir(parents=True, exist_ok=True)
        self.sessions_path.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.sessions_path / f"{session_id}.jsonl"

    # REMOVED: _chunk_path, _list_chunks, _get_current_chunk_index, _count_messages_in_chunk

    def _read_index(self) -> list[HistorySession]:
        """Read all session entries from index.jsonl."""
        # ... unchanged

    def _write_index(self, sessions: list[HistorySession]) -> None:
        """Write all session entries to index.jsonl."""
        # ... unchanged

    def _find_session_index(
        self, sessions: list[HistorySession], session_id: str
    ) -> int:
        """Find the index of a session in the list."""
        # ... unchanged

    def create_session(
        self,
        agent_id: str,
        session_id: str,
        source: "EventSource",
    ) -> dict[str, Any]:
        """Create a new conversation session."""
        now = _now_iso()
        session = HistorySession(
            id=session_id,
            agent_id=agent_id,
            source=source,
            title=None,
            message_count=0,
            created_at=now,
            updated_at=now,
        )

        # Append to index
        with open(self.index_path, "a") as f:
            f.write(session.model_dump_json() + "\n")

        # Create session file
        self._session_path(session_id).touch()

        return session.model_dump()

    def save_message(self, session_id: str, message: HistoryMessage) -> None:
        """Save a message to history."""
        sessions = self._read_index()
        idx = self._find_session_index(sessions, session_id)
        if idx < 0:
            raise ValueError(f"Session not found: {session_id}")

        session = sessions[idx]

        # Append message to session file
        session_file = self._session_path(session_id)
        with open(session_file, "a") as f:
            f.write(message.model_dump_json() + "\n")

        # Update index
        session.message_count += 1
        session.updated_at = _now_iso()

        # Auto-generate title from first user message
        if session.title is None and message.role == "user":
            title = message.content[:50]
            if len(message.content) > 50:
                title += "..."
            session.title = title

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        self._write_index(sessions)

    def update_session_title(self, session_id: str, title: str) -> None:
        """Update a session's title."""
        # ... unchanged

    def list_sessions(self) -> list[HistorySession]:
        """List all sessions, most recently updated first."""
        # ... unchanged

    def get_messages(self, session_id: str) -> list[HistoryMessage]:
        """Get all messages for a session.

        Token limiting is handled by ContextGuard, not here.
        """
        session_file = self._session_path(session_id)
        if not session_file.exists():
            return []

        messages: list[HistoryMessage] = []
        with open(session_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(HistoryMessage.model_validate_json(line))
                    except Exception:
                        continue

        return messages
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ -k history -v`
Expected: May have failures - update tests as needed

**Step 5: Update tests if needed**

Remove any tests that reference `chunk_count` or `max_history_file_size`.

**Step 6: Commit**

```bash
git add src/picklebot/core/history.py tests/
git commit -m "refactor: remove chunking from HistoryStore"
```

---

## Task 6: Remove max_history_file_size from Config

**Files:**
- Modify: `src/picklebot/utils/config.py`
- Modify: `tests/test_config.py` (if needed)

**Step 1: Find and remove max_history_file_size**

```bash
grep -r "max_history_file_size" src/picklebot/
```

**Step 2: Remove from Config class**

Remove any `max_history_file_size` field from the Config class and its usage in `HistoryStore.from_config()`.

**Step 3: Run tests**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/utils/config.py
git commit -m "refactor: remove max_history_file_size from Config"
```

---

## Task 7: Remove max_history from AgentSession

**Files:**
- Modify: `src/picklebot/core/agent.py`

**Step 1: Remove max_history field from AgentSession**

```python
# Modify src/picklebot/core/agent.py

@dataclass
class AgentSession:
    """Runtime state for a single conversation."""

    session_id: str
    agent_id: str
    shared_context: "SharedContext"  # Shared app context (DI container)
    agent: Agent  # Reference to parent agent for LLM access
    tools: ToolRegistry  # Session's own tool registry
    source: "EventSource"  # Event source (e.g., "telegram:user_123", "cron:daily")
    # REMOVED: max_history: int

    messages: list[Message] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
```

**Step 2: Remove get_source_settings function**

```python
# DELETE this function from src/picklebot/core/agent.py

def get_source_settings(source: EventSource) -> tuple[int, bool]:
    # ... delete entire function
```

**Step 3: Update new_session method**

```python
# Modify src/picklebot/core/agent.py - Agent.new_session()

def new_session(
    self,
    source: "EventSource",
    session_id: str | None = None,
) -> "AgentSession":
    """
    Create a new conversation session.

    Args:
        source: Event source (e.g., "telegram:user_123", "cron:daily")
        session_id: Optional session_id to use (for recovery scenarios)

    Returns:
        A new Session instance with source-appropriate tools.
    """
    session_id = session_id or str(uuid.uuid4())

    # Build tools for this session
    # Note: include_post_message logic moved to be source-based
    include_post_message = source.is_cron
    tools = self._build_tools(include_post_message)

    session = AgentSession(
        session_id=session_id,
        agent_id=self.agent_def.id,
        shared_context=self.context,
        agent=self,
        tools=tools,
        source=source,
    )

    self.context.history_store.create_session(self.agent_def.id, session_id, source)
    return session
```

**Step 4: Update resume_session method**

```python
# Modify src/picklebot/core/agent.py - Agent.resume_session()

def resume_session(self, session_id: str) -> "AgentSession":
    """
    Load an existing conversation session.

    Args:
        session_id: The ID of the session to load.

    Returns:
        A Session instance with self as the agent reference.
    """
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

    # Get all messages (no max_history limit)
    history_messages = self.context.history_store.get_messages(session_id)

    # Convert HistoryMessage to litellm Message format
    messages: list[Message] = [msg.to_message() for msg in history_messages]

    # Build tools for resumed session
    tools = self._build_tools(include_post_message)

    return AgentSession(
        session_id=session_info.id,
        agent_id=session_info.agent_id,
        shared_context=self.context,
        agent=self,
        tools=tools,
        source=source,
        messages=messages,
    )
```

**Step 5: Update get_history method**

```python
# Modify src/picklebot/core/agent.py - AgentSession.get_history()

def get_history(self) -> list[Message]:
    """Get all messages for LLM context.

    Note: Token limiting is handled by ContextGuard, not here.
    """
    return self.messages
```

**Step 6: Run tests**

Run: `uv run pytest tests/ -v`
Expected: May need to update some tests

**Step 7: Commit**

```bash
git add src/picklebot/core/agent.py
git commit -m "refactor: remove max_history from AgentSession"
```

---

## Task 8: Integrate ContextGuard into AgentSession

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_context_guard.py

import pytest
from unittest.mock import MagicMock, patch


class TestCheckAndCompact:
    def test_check_and_compact_under_threshold(self):
        """Returns messages unchanged when under threshold."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=10000)

        # Mock session
        session = MagicMock()
        session.agent.llm.model = "gpt-4"

        messages = [{"role": "user", "content": "Hello"}]

        result = guard.check_and_compact(session, messages)

        # Should return same messages (under threshold)
        assert result == messages

    def test_check_and_compact_over_threshold_triggers_compaction(self):
        """Triggers compaction when over threshold."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=10)  # Very low threshold

        # Mock session and context
        session = MagicMock()
        session.agent.llm.model = "gpt-4"
        session.agent.new_session.return_value = MagicMock(session_id="new-session-id")
        session.source = "test:user"

        mock_context = MagicMock()
        mock_context.config.set_runtime = MagicMock()
        guard.shared_context = mock_context

        # Many messages to exceed threshold
        messages = [{"role": "user", "content": f"Message {i} " * 100} for i in range(20)]

        with patch.object(guard, '_generate_summary', return_value="Summary"):
            result = guard.check_and_compact(session, messages)

        # Should return compacted messages
        assert len(result) < len(messages)
        assert result[0]["role"] == "user"
        assert "[Previous conversation summary]" in result[0]["content"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestCheckAndCompact -v`
Expected: FAIL

**Step 3: Implement check_and_compact**

```python
# Add to ContextGuard class in src/picklebot/core/context_guard.py

    def check_and_compact(
        self,
        session: "AgentSession",
        messages: list[Message],
    ) -> list[Message]:
        """Check token count, compact and roll session if needed.

        Args:
            session: Current agent session
            messages: Current message list

        Returns:
            Messages to use (either original or compacted)
        """
        token_count = self.count_tokens(messages, session.agent.llm.model)

        if token_count < self.token_threshold:
            return messages

        # Over threshold - compact and roll
        return self._compact_and_roll(session, messages)

    def _compact_and_roll(
        self,
        session: "AgentSession",
        messages: list[Message],
    ) -> list[Message]:
        """Compact history, roll to new session, return new messages.

        Args:
            session: Current agent session
            messages: Current message list

        Returns:
            Compacted message list
        """
        import asyncio

        # Generate summary of older messages
        summary = asyncio.get_event_loop().run_until_complete(
            self._generate_summary(session, messages)
        )

        # Roll to new session
        self._roll_session(session, summary)

        # Return compacted messages
        return self._build_compacted_messages(summary, messages)

    def _roll_session(self, session: "AgentSession", summary: str) -> str:
        """Create new session, update source mapping, return new ID.

        Args:
            session: Current agent session
            summary: Generated summary (unused here but available)

        Returns:
            New session ID
        """
        # Create new session
        new_session = session.agent.new_session(session.source)

        # Update source → session mapping
        self.shared_context.config.set_runtime(
            f"sources.{session.source}",
            {"session_id": new_session.session_id},
        )

        return new_session.session_id
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py::TestCheckAndCompact -v`
Expected: May need adjustments for async handling

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: implement check_and_compact with session rolling"
```

---

## Task 9: Implement async summary generation

**Files:**
- Modify: `src/picklebot/core/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_context_guard.py

class TestSummaryGeneration:
    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """Generate summary of older messages."""
        from picklebot.core.context_guard import ContextGuard

        guard = ContextGuard(token_threshold=1000)

        # Mock session with LLM
        session = MagicMock()
        session.agent.llm.chat = MagicMock(return_value=asyncio.coroutine(lambda: "Summary text")())

        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
            {"role": "user", "content": "Tell me more"},
            {"role": "assistant", "content": "It's high-level and interpreted."},
        ]

        summary = await guard._generate_summary(session, messages)

        assert summary == "Summary text"
        session.agent.llm.chat.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context_guard.py::TestSummaryGeneration -v`
Expected: FAIL

**Step 3: Implement _generate_summary**

```python
# Add to ContextGuard class in src/picklebot/core/context_guard.py

    async def _generate_summary(
        self,
        session: "AgentSession",
        messages: list[Message],
    ) -> str:
        """Generate summary of older messages using agent's LLM.

        Args:
            session: Current agent session
            messages: Current message list

        Returns:
            Generated summary text
        """
        keep_count = max(4, int(len(messages) * 0.2))
        compress_count = max(2, int(len(messages) * 0.5))
        compress_count = min(compress_count, len(messages) - keep_count)

        old_messages = messages[:compress_count]

        # Serialize old messages for summary
        old_text = self._serialize_messages_for_summary(old_messages)

        summary_prompt = f"""Summarize the conversation so far. Keep it factual and concise. Focus on key decisions, facts, and user preferences discovered:

{old_text}"""

        # Use agent's LLM to generate summary
        response, _ = await session.agent.llm.chat(
            [{"role": "user", "content": summary_prompt}],
            [],  # No tools needed
        )
        return response
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context_guard.py::TestSummaryGeneration -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/context_guard.py tests/test_context_guard.py
git commit -m "feat: implement async summary generation"
```

---

## Task 10: Fix async handling in _compact_and_roll

**Files:**
- Modify: `src/picklebot/core/context_guard.py`

**Step 1: Refactor to make check_and_compact async**

The current implementation uses `run_until_complete` which is problematic. Since `chat()` is already async, we can make `check_and_compact` async too.

```python
# Modify src/picklebot/core/context_guard.py

    async def check_and_compact(
        self,
        session: "AgentSession",
        messages: list[Message],
    ) -> list[Message]:
        """Check token count, compact and roll session if needed.

        Args:
            session: Current agent session
            messages: Current message list

        Returns:
            Messages to use (either original or compacted)
        """
        token_count = self.count_tokens(messages, session.agent.llm.model)

        if token_count < self.token_threshold:
            return messages

        # Over threshold - compact and roll
        return await self._compact_and_roll(session, messages)

    async def _compact_and_roll(
        self,
        session: "AgentSession",
        messages: list[Message],
    ) -> list[Message]:
        """Compact history, roll to new session, return new messages.

        Args:
            session: Current agent session
            messages: Current message list

        Returns:
            Compacted message list
        """
        # Generate summary of older messages
        summary = await self._generate_summary(session, messages)

        # Roll to new session
        self._roll_session(session, summary)

        # Return compacted messages
        return self._build_compacted_messages(summary, messages)
```

**Step 2: Run all context guard tests**

Run: `uv run pytest tests/test_context_guard.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/picklebot/core/context_guard.py
git commit -m "refactor: make check_and_compact async"
```

---

## Task 11: Wire ContextGuard into AgentSession.chat()

**Files:**
- Modify: `src/picklebot/core/agent.py`

**Step 1: Create ContextGuard in Agent.new_session()**

```python
# Modify src/picklebot/core/agent.py - add import at top

from picklebot.core.context_guard import ContextGuard

# Modify Agent.new_session()

def new_session(
    self,
    source: "EventSource",
    session_id: str | None = None,
) -> "AgentSession":
    session_id = session_id or str(uuid.uuid4())

    include_post_message = source.is_cron
    tools = self._build_tools(include_post_message)

    # Create context guard for this session
    context_guard = ContextGuard(
        shared_context=self.context,
        token_threshold=self._get_token_threshold(),
    )

    session = AgentSession(
        session_id=session_id,
        agent_id=self.agent_def.id,
        shared_context=self.context,
        agent=self,
        tools=tools,
        source=source,
        context_guard=context_guard,
    )

    self.context.history_store.create_session(self.agent_def.id, session_id, source)
    return session

def _get_token_threshold(self) -> int:
    """Get token threshold based on model's context window."""
    # Default to 80% of 200k context
    # TODO: Make this configurable per model
    return 160000
```

**Step 2: Add context_guard field to AgentSession**

```python
# Modify src/picklebot/core/agent.py - AgentSession dataclass

@dataclass
class AgentSession:
    """Runtime state for a single conversation."""

    session_id: str
    agent_id: str
    shared_context: "SharedContext"
    agent: Agent
    tools: ToolRegistry
    source: "EventSource"
    context_guard: ContextGuard  # Added

    messages: list[Message] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
```

**Step 3: Use context_guard in chat()**

```python
# Modify src/picklebot/core/agent.py - AgentSession.chat()

async def chat(self, message: str) -> str:
    """
    Send a message to the LLM and get a response.

    Args:
        message: User message

    Returns:
        Assistant's response text
    """
    user_msg: Message = {"role": "user", "content": message}
    self.add_message(user_msg)

    tool_schemas = self.tools.get_tool_schemas()

    while True:
        messages = self._build_messages()

        # Check context and compact if needed
        messages = await self.context_guard.check_and_compact(self, messages)

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

        self.add_message(assistant_msg)

        if not tool_calls:
            break

        await self._handle_tool_calls(tool_calls)

        continue

    return content
```

**Step 4: Update resume_session to create ContextGuard**

```python
# Modify src/picklebot/core/agent.py - Agent.resume_session()

def resume_session(self, session_id: str) -> "AgentSession":
    session_query = [
        session
        for session in self.context.history_store.list_sessions()
        if session.id == session_id
    ]
    if not session_query:
        raise ValueError(f"Session not found: {session_id}")

    session_info = session_query[0]

    source = session_info.get_source()
    include_post_message = source.is_cron

    history_messages = self.context.history_store.get_messages(session_id)
    messages: list[Message] = [msg.to_message() for msg in history_messages]

    tools = self._build_tools(include_post_message)

    # Create context guard
    context_guard = ContextGuard(
        shared_context=self.context,
        token_threshold=self._get_token_threshold(),
    )

    return AgentSession(
        session_id=session_info.id,
        agent_id=session_info.agent_id,
        shared_context=self.context,
        agent=self,
        tools=tools,
        source=source,
        messages=messages,
        context_guard=context_guard,
    )
```

**Step 5: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: PASS (may need minor fixes)

**Step 6: Commit**

```bash
git add src/picklebot/core/agent.py
git commit -m "feat: integrate ContextGuard into AgentSession.chat()"
```

---

## Task 12: Run full test suite and fix any issues

**Files:**
- Various test files as needed

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

**Step 2: Fix any failing tests**

Address any test failures related to:
- Removed `max_history` parameter
- Removed `chunk_count` field
- New `context_guard` field in AgentSession

**Step 3: Commit fixes**

```bash
git add tests/
git commit -m "fix: update tests for context guard integration"
```

---

## Task 13: Format, lint, and final verification

**Step 1: Format code**

```bash
uv run black .
```

**Step 2: Lint code**

```bash
uv run ruff check .
```

**Step 3: Fix any lint issues**

**Step 4: Run tests one more time**

```bash
uv run pytest tests/ -v
```

**Step 5: Final commit**

```bash
git add .
git commit -m "style: format and lint for context guard feature"
```

---

## Summary

This implementation plan covers:

1. **ContextGuard class** - Token counting, message serialization, compaction logic
2. **HistoryStore simplification** - Remove chunking, single file per session
3. **AgentSession changes** - Remove max_history, integrate ContextGuard
4. **Session rolling** - Automatic source mapping update on compaction

The result is a simpler, more scalable context management system that proactively handles context limits through token-aware compaction and seamless session handoff.
