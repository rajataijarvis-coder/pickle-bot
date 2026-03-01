# Session Source Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove SessionMode, add source/context persistence to sessions, derive behavior from source.

**Architecture:** Sessions store `source` (string) and `context` (serialized MessageContext) in HistorySession. A `get_source_settings(source)` helper returns `(max_history, post_message)`. Agent.new_session takes source/context instead of mode. Workers pass source/context from events.

**Tech Stack:** Python dataclasses, Pydantic models, existing HistoryStore JSONL format

---

### Task 1: Add get_source_settings Helper

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Test: `tests/core/test_agent.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_agent.py`:

```python
import pytest
from picklebot.core.agent import get_source_settings


class TestGetSourceSettings:
    """Tests for source-based settings derivation."""

    def test_cron_source_returns_job_settings(self):
        """Cron sources should return job settings."""
        max_history, post_message = get_source_settings("cron:daily_summary")
        assert max_history == 50
        assert post_message is True

    def test_cron_source_with_complex_id(self):
        """Cron sources with complex IDs should return job settings."""
        max_history, post_message = get_source_settings("cron:my-cron-job-123")
        assert max_history == 50
        assert post_message is True

    def test_telegram_source_returns_chat_settings(self):
        """Telegram sources should return chat settings."""
        max_history, post_message = get_source_settings("telegram:user_123")
        assert max_history == 100
        assert post_message is False

    def test_discord_source_returns_chat_settings(self):
        """Discord sources should return chat settings."""
        max_history, post_message = get_source_settings("discord:member_456")
        assert max_history == 100
        assert post_message is False

    def test_agent_source_returns_chat_settings(self):
        """Agent (subagent) sources should return chat settings."""
        max_history, post_message = get_source_settings("agent:cookie")
        assert max_history == 100
        assert post_message is False

    def test_cli_source_returns_chat_settings(self):
        """CLI sources should return chat settings."""
        max_history, post_message = get_source_settings("cli:default")
        assert max_history == 100
        assert post_message is False

    def test_retry_source_returns_chat_settings(self):
        """Retry sources should return chat settings."""
        max_history, post_message = get_source_settings("retry")
        assert max_history == 100
        assert post_message is False

    def test_unknown_source_returns_chat_settings(self):
        """Unknown sources should default to chat settings."""
        max_history, post_message = get_source_settings("unknown")
        assert max_history == 100
        assert post_message is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_agent.py::TestGetSourceSettings -v`
Expected: FAIL - `ImportError: cannot import name 'get_source_settings'`

**Step 3: Implement get_source_settings**

Add to `src/picklebot/core/agent.py` (after imports, before SessionMode):

```python
def get_source_settings(source: str) -> tuple[int, bool]:
    """Return (max_history, post_message) settings for a given source.

    Args:
        source: Event source string (e.g., "cron:daily", "telegram:user_123")

    Returns:
        Tuple of (max_history, post_message_enabled)
    """
    if source.startswith("cron:"):
        return (50, True)
    return (100, False)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_agent.py::TestGetSourceSettings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/agent.py tests/core/test_agent.py
git commit -m "feat(agent): add get_source_settings helper for source-based config"
```

---

### Task 2: Update HistorySession Model

**Files:**
- Modify: `src/picklebot/core/history.py`
- Test: `tests/core/test_history.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_history.py`:

```python
import pytest
from picklebot.core.history import HistorySession


class TestHistorySessionWithSource:
    """Tests for HistorySession with source and context fields."""

    def test_history_session_has_source_field(self):
        """HistorySession should accept source field."""
        session = HistorySession(
            id="test-session",
            agent_id="pickle",
            source="telegram:user_123",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert session.source == "telegram:user_123"

    def test_history_session_has_context_field(self):
        """HistorySession should accept context field."""
        context_data = {"type": "TelegramContext", "data": {"user_id": "123", "chat_id": "456"}}
        session = HistorySession(
            id="test-session",
            agent_id="pickle",
            source="telegram:user_123",
            context=context_data,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert session.context == context_data

    def test_history_session_context_defaults_to_none(self):
        """HistorySession context should default to None."""
        session = HistorySession(
            id="test-session",
            agent_id="pickle",
            source="cron:daily",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert session.context is None

    def test_history_session_json_roundtrip_with_source(self):
        """HistorySession with source should serialize/deserialize correctly."""
        original = HistorySession(
            id="test-session",
            agent_id="pickle",
            source="telegram:user_123",
            context={"type": "TelegramContext", "data": {"user_id": "123"}},
            chunk_count=1,
            title="Test Chat",
            message_count=5,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )

        json_str = original.model_dump_json()
        restored = HistorySession.model_validate_json(json_str)

        assert restored.source == original.source
        assert restored.context == original.context
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_history.py::TestHistorySessionWithSource -v`
Expected: FAIL - `ValidationError` or missing fields

**Step 3: Update HistorySession model**

Modify `src/picklebot/core/history.py`:

```python
class HistorySession(BaseModel):
    """Session metadata - stored in index.jsonl."""

    id: str
    agent_id: str
    source: str  # Origin of session (e.g., "telegram:user_123", "cron:daily")
    context: dict[str, Any] | None = None  # Serialized MessageContext
    chunk_count: int = 1
    title: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_history.py::TestHistorySessionWithSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/history.py tests/core/test_history.py
git commit -m "feat(history): add source and context fields to HistorySession"
```

---

### Task 3: Update HistoryStore.create_session

**Files:**
- Modify: `src/picklebot/core/history.py`
- Test: `tests/core/test_history.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_history.py`:

```python
from pathlib import Path
import tempfile
from picklebot.core.history import HistoryStore


class TestHistoryStoreWithSource:
    """Tests for HistoryStore with source/context support."""

    @pytest.fixture
    def store(self):
        """Create a temporary HistoryStore for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield HistoryStore(Path(tmpdir))

    def test_create_session_with_source(self, store):
        """create_session should store source."""
        result = store.create_session(
            agent_id="pickle",
            session_id="test-123",
            source="telegram:user_456",
        )
        assert result["source"] == "telegram:user_456"

    def test_create_session_with_source_and_context(self, store):
        """create_session should store source and context."""
        context = {"type": "TelegramContext", "data": {"user_id": "456", "chat_id": "789"}}
        result = store.create_session(
            agent_id="pickle",
            session_id="test-123",
            source="telegram:user_456",
            context=context,
        )
        assert result["source"] == "telegram:user_456"
        assert result["context"] == context

    def test_list_sessions_includes_source(self, store):
        """list_sessions should return sessions with source."""
        store.create_session(
            agent_id="pickle",
            session_id="test-123",
            source="cron:daily",
        )
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].source == "cron:daily"

    def test_get_session_by_id(self, store):
        """Should be able to get a specific session by ID."""
        store.create_session(
            agent_id="pickle",
            session_id="test-123",
            source="telegram:user_456",
            context={"type": "TelegramContext", "data": {"user_id": "456"}},
        )

        # Find the session
        sessions = store.list_sessions()
        session = next((s for s in sessions if s.id == "test-123"), None)

        assert session is not None
        assert session.source == "telegram:user_456"
        assert session.context is not None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_history.py::TestHistoryStoreWithSource -v`
Expected: FAIL - `TypeError: create_session() got unexpected keyword argument 'source'`

**Step 3: Update create_session method**

Modify `src/picklebot/core/history.py`:

```python
def create_session(
    self,
    agent_id: str,
    session_id: str,
    source: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new conversation session.

    Args:
        agent_id: ID of the agent
        session_id: Unique session identifier
        source: Origin of the session (e.g., "telegram:user_123")
        context: Optional serialized MessageContext

    Returns:
        Session metadata dict
    """
    now = _now_iso()
    session = HistorySession(
        id=session_id,
        agent_id=agent_id,
        source=source,
        context=context,
        chunk_count=1,
        title=None,
        message_count=0,
        created_at=now,
        updated_at=now,
    )

    # Append to index
    with open(self.index_path, "a") as f:
        f.write(session.model_dump_json() + "\n")

    # Create first chunk file
    self._chunk_path(session_id, 1).touch()

    return session.model_dump()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_history.py::TestHistoryStoreWithSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/history.py tests/core/test_history.py
git commit -m "feat(history): update create_session to accept source and context"
```

---

### Task 4: Update AgentSession and Agent.new_session

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Test: `tests/core/test_agent.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_agent.py`:

```python
from picklebot.core.agent import AgentSession, get_source_settings


class TestAgentSessionWithSource:
    """Tests for AgentSession with source field."""

    def test_agent_session_has_source_field(self):
        """AgentSession should have source field."""
        # This will fail until we update the dataclass
        from dataclasses import fields
        field_names = [f.name for f in fields(AgentSession)]
        assert "source" in field_names

    def test_agent_session_has_context_field(self):
        """AgentSession should have context field."""
        from dataclasses import fields
        field_names = [f.name for f in fields(AgentSession)]
        assert "context" in field_names


class TestAgentNewSessionWithSource:
    """Tests for Agent.new_session with source parameter."""

    @pytest.fixture
    def mock_context(self, tmp_path):
        """Create a mock SharedContext for testing."""
        from unittest.mock import MagicMock
        from picklebot.core.history import HistoryStore

        context = MagicMock()
        context.config.chat_max_history = 100
        context.config.job_max_history = 50
        context.config.messagebus = MagicMock()
        context.history_store = HistoryStore(tmp_path)
        context.skill_loader = MagicMock()
        context.skill_loader.list_skills.return_value = []

        return context

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock AgentDef for testing."""
        from unittest.mock import MagicMock
        agent_def = MagicMock()
        agent_def.id = "test-agent"
        agent_def.llm = {"model": "gpt-4"}
        agent_def.system_prompt = "You are a test agent."
        agent_def.allow_skills = False
        agent_def.max_concurrency = 1
        return agent_def

    def test_new_session_accepts_source(self, mock_context, mock_agent_def):
        """new_session should accept source parameter."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="telegram:user_123")

        assert session.source == "telegram:user_123"

    def test_new_session_accepts_context(self, mock_context, mock_agent_def):
        """new_session should accept context parameter."""
        from picklebot.core.agent import Agent
        from picklebot.messagebus.cli_bus import CliContext

        agent = Agent(mock_agent_def, mock_context)
        context = CliContext(user_id="test-user")
        session = agent.new_session(source="cli:test-user", context=context)

        assert session.context is not None
        assert session.context.user_id == "test-user"

    def test_new_session_derives_max_history_from_source_cron(self, mock_context, mock_agent_def):
        """new_session should derive max_history from source for cron."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="cron:daily_job")

        assert session.max_history == 50

    def test_new_session_derives_max_history_from_source_chat(self, mock_context, mock_agent_def):
        """new_session should derive max_history from source for chat."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="telegram:user_123")

        assert session.max_history == 100

    def test_new_session_includes_post_message_for_cron(self, mock_context, mock_agent_def):
        """new_session should include post_message tool for cron sources."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="cron:daily_job")

        tool_names = session.tools.list_tools()
        assert "post_message" in tool_names

    def test_new_session_excludes_post_message_for_chat(self, mock_context, mock_agent_def):
        """new_session should NOT include post_message tool for chat sources."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="telegram:user_123")

        tool_names = session.tools.list_tools()
        assert "post_message" not in tool_names

    def test_new_session_persists_source_to_history(self, mock_context, mock_agent_def):
        """new_session should persist source to HistoryStore."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        session = agent.new_session(source="telegram:user_123")

        # Check that history store has the session with source
        sessions = mock_context.history_store.list_sessions()
        stored = next((s for s in sessions if s.id == session.session_id), None)
        assert stored is not None
        assert stored.source == "telegram:user_123"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_agent.py::TestAgentSessionWithSource tests/core/test_agent.py::TestAgentNewSessionWithSource -v`
Expected: FAIL - various import/type errors

**Step 3: Update AgentSession dataclass**

Modify `src/picklebot/core/agent.py`:

```python
@dataclass
class AgentSession:
    """Runtime state for a single conversation."""

    session_id: str
    agent_id: str
    source: str  # Origin of session (e.g., "telegram:user_123", "cron:daily")
    context: "MessageContext | None"  # Platform context (TelegramContext, etc.)
    shared_context: "SharedContext"
    agent: Agent
    tools: ToolRegistry
    max_history: int

    messages: list[Message] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
```

**Step 4: Update new_session method**

Replace `new_session` in `src/picklebot/core/agent.py`:

```python
def new_session(
    self,
    source: str,
    context: "MessageContext | None" = None,
    session_id: str | None = None,
) -> AgentSession:
    """
    Create a new conversation session.

    Args:
        source: Origin of the session (e.g., "telegram:user_123", "cron:daily")
        context: Optional MessageContext for platform-specific data
        session_id: Optional session_id to use (for recovery scenarios)

    Returns:
        A new AgentSession instance.
    """
    session_id = session_id or str(uuid.uuid4())

    # Derive settings from source
    max_history, include_post_message = get_source_settings(source)

    # Build tools for this session
    tools = self._build_tools(include_post_message)

    # Serialize context for storage
    context_dict = None
    if context is not None:
        context_dict = {
            "type": type(context).__name__,
            "data": {
                k: getattr(context, k)
                for k in context.__dataclass_fields__
            }
        }

    session = AgentSession(
        session_id=session_id,
        agent_id=self.agent_def.id,
        source=source,
        context=context,
        shared_context=self.context,
        agent=self,
        tools=tools,
        max_history=max_history,
    )

    self.context.history_store.create_session(
        agent_id=self.agent_def.id,
        session_id=session_id,
        source=source,
        context=context_dict,
    )
    return session
```

**Step 5: Update _build_tools method**

Replace `_build_tools` in `src/picklebot/core/agent.py`:

```python
def _build_tools(self, include_post_message: bool) -> ToolRegistry:
    """
    Build a ToolRegistry with appropriate tools.

    Args:
        include_post_message: Whether to include the post_message tool

    Returns:
        ToolRegistry with base tools + optional tools
    """
    registry = ToolRegistry.with_builtins()

    # Register skill tool if allowed
    if self.agent_def.allow_skills:
        skill_tool = create_skill_tool(self.context.skill_loader)
        if skill_tool:
            registry.register(skill_tool)

    # Register subagent dispatch tool if other agents exist
    subagent_tool = create_subagent_dispatch_tool(self.agent_def.id, self.context)
    if subagent_tool:
        registry.register(subagent_tool)

    websearch_tool = create_websearch_tool(self.context)
    if websearch_tool:
        registry.register(websearch_tool)

    webread_tool = create_webread_tool(self.context)
    if webread_tool:
        registry.register(webread_tool)

    # Register post_message tool if requested (for cron jobs)
    if include_post_message:
        post_tool = create_post_message_tool(self.context)
        if post_tool:
            registry.register(post_tool)

    return registry
```

**Step 6: Add import for MessageContext**

Add to imports in `src/picklebot/core/agent.py`:

```python
if TYPE_CHECKING:
    from picklebot.core.context import SharedContext
    from picklebot.core.agent_loader import AgentDef
    from picklebot.provider.llm import LLMToolCall
    from picklebot.messagebus.base import MessageContext
```

**Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_agent.py::TestAgentSessionWithSource tests/core/test_agent.py::TestAgentNewSessionWithSource -v`
Expected: Some tests may fail due to field name change (`context` -> `shared_context`)

**Step 8: Fix any field name issues**

The tests use `mock_context` which gets passed as the old `context` parameter. Update to use `shared_context`:

Update tests to pass context correctly and update any references from `session.context` to `session.shared_context` where accessing SharedContext.

**Step 9: Run tests again**

Run: `uv run pytest tests/core/test_agent.py::TestAgentSessionWithSource tests/core/test_agent.py::TestAgentNewSessionWithSource -v`
Expected: PASS

**Step 10: Commit**

```bash
git add src/picklebot/core/agent.py tests/core/test_agent.py
git commit -m "feat(agent): update new_session to use source instead of mode"
```

---

### Task 5: Update Agent.resume_session

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Test: `tests/core/test_agent.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_agent.py`:

```python
class TestAgentResumeSessionWithSource:
    """Tests for Agent.resume_session loading source from history."""

    @pytest.fixture
    def mock_context(self, tmp_path):
        """Create a mock SharedContext for testing."""
        from unittest.mock import MagicMock
        from picklebot.core.history import HistoryStore

        context = MagicMock()
        context.config.chat_max_history = 100
        context.config.job_max_history = 50
        context.config.messagebus = MagicMock()
        context.history_store = HistoryStore(tmp_path)
        context.skill_loader = MagicMock()
        context.skill_loader.list_skills.return_value = []

        return context

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock AgentDef for testing."""
        from unittest.mock import MagicMock
        agent_def = MagicMock()
        agent_def.id = "test-agent"
        agent_def.llm = {"model": "gpt-4"}
        agent_def.system_prompt = "You are a test agent."
        agent_def.allow_skills = False
        agent_def.max_concurrency = 1
        return agent_def

    def test_resume_session_loads_source(self, mock_context, mock_agent_def):
        """resume_session should load source from history."""
        from picklebot.core.agent import Agent

        # First create a session with source
        agent = Agent(mock_agent_def, mock_context)
        original = agent.new_session(source="telegram:user_456")

        # Now resume it
        resumed = agent.resume_session(original.session_id)
        assert resumed.source == "telegram:user_456"

    def test_resume_session_loads_context(self, mock_context, mock_agent_def):
        """resume_session should load context from history."""
        from picklebot.core.agent import Agent
        from picklebot.messagebus.cli_bus import CliContext

        # First create a session with context
        agent = Agent(mock_agent_def, mock_context)
        cli_context = CliContext(user_id="test-cli-user")
        original = agent.new_session(source="cli:test-cli-user", context=cli_context)

        # Now resume it
        resumed = agent.resume_session(original.session_id)
        assert resumed.context is not None
        assert resumed.context.user_id == "test-cli-user"

    def test_resume_session_derives_max_history_cron(self, mock_context, mock_agent_def):
        """resume_session should derive max_history from stored source (cron)."""
        from picklebot.core.agent import Agent

        # Create a cron session
        agent = Agent(mock_agent_def, mock_context)
        original = agent.new_session(source="cron:daily_job")

        # Resume it
        resumed = agent.resume_session(original.session_id)
        assert resumed.max_history == 50

    def test_resume_session_derives_max_history_chat(self, mock_context, mock_agent_def):
        """resume_session should derive max_history from stored source (chat)."""
        from picklebot.core.agent import Agent

        # Create a chat session
        agent = Agent(mock_agent_def, mock_context)
        original = agent.new_session(source="discord:member_789")

        # Resume it
        resumed = agent.resume_session(original.session_id)
        assert resumed.max_history == 100

    def test_resume_session_includes_post_message_for_cron(self, mock_context, mock_agent_def):
        """resume_session should include post_message for cron sources."""
        from picklebot.core.agent import Agent

        agent = Agent(mock_agent_def, mock_context)
        original = agent.new_session(source="cron:daily_job")

        resumed = agent.resume_session(original.session_id)
        tool_names = resumed.tools.list_tools()
        assert "post_message" in tool_names

    def test_resume_session_defaults_unknown_source(self, mock_context, mock_agent_def):
        """resume_session should handle sessions without source (migration)."""
        from picklebot.core.agent import Agent

        # Create a session directly in history without source (simulating old data)
        mock_context.history_store.create_session(
            agent_id="test-agent",
            session_id="old-session-123",
            source="unknown",  # Will be set by updated create_session
        )

        agent = Agent(mock_agent_def, mock_context)
        resumed = agent.resume_session("old-session-123")

        assert resumed.source == "unknown"
        assert resumed.max_history == 100  # Chat default
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_agent.py::TestAgentResumeSessionWithSource -v`
Expected: FAIL - various errors due to old resume_session signature

**Step 3: Add context deserialization helper**

Add to `src/picklebot/core/agent.py` (after imports):

```python
def _deserialize_context(data: dict[str, Any] | None) -> "MessageContext | None":
    """Deserialize a dict back to MessageContext."""
    if data is None:
        return None

    context_type = data.get("type")
    context_data = data.get("data", {})

    if context_type == "TelegramContext":
        from picklebot.messagebus.telegram_bus import TelegramContext
        return TelegramContext(**context_data)
    elif context_type == "DiscordContext":
        from picklebot.messagebus.discord_bus import DiscordContext
        return DiscordContext(**context_data)
    elif context_type == "CliContext":
        from picklebot.messagebus.cli_bus import CliContext
        return CliContext(**context_data)

    return None
```

**Step 4: Update resume_session method**

Replace `resume_session` in `src/picklebot/core/agent.py`:

```python
def resume_session(self, session_id: str) -> AgentSession:
    """
    Load an existing conversation session.

    Args:
        session_id: The ID of the session to load.

    Returns:
        An AgentSession with history loaded from storage.
    """
    # Find the session in history
    sessions = self.context.history_store.list_sessions()
    session_info = next((s for s in sessions if s.id == session_id), None)

    if not session_info:
        raise ValueError(f"Session not found: {session_id}")

    # Get source and context from stored session
    source = session_info.source or "unknown"
    context = _deserialize_context(session_info.context)

    # Derive settings from source
    max_history, include_post_message = get_source_settings(source)

    # Load message history
    history_messages = self.context.history_store.get_messages(
        session_id, max_history=max_history
    )
    messages: list[Message] = [msg.to_message() for msg in history_messages]

    # Build tools
    tools = self._build_tools(include_post_message)

    return AgentSession(
        session_id=session_info.id,
        agent_id=session_info.agent_id,
        source=source,
        context=context,
        shared_context=self.context,
        agent=self,
        tools=tools,
        max_history=max_history,
        messages=messages,
    )
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_agent.py::TestAgentResumeSessionWithSource -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/picklebot/core/agent.py tests/core/test_agent.py
git commit -m "feat(agent): update resume_session to load source from history"
```

---

### Task 6: Remove SessionMode Enum

**Files:**
- Modify: `src/picklebot/core/agent.py`
- Test: Run all tests

**Step 1: Remove SessionMode class**

Delete from `src/picklebot/core/agent.py`:

```python
class SessionMode(str, Enum):
    """Session mode determines history limit behavior."""

    CHAT = "chat"
    JOB = "job"
```

**Step 2: Run all tests to find breakages**

Run: `uv run pytest tests/ -v`
Expected: Some failures in workers/tools that import SessionMode

**Step 3: Check each failing file**

List files that import SessionMode:
```bash
grep -r "SessionMode" src/
```

**Step 4: Commit**

```bash
git add src/picklebot/core/agent.py
git commit -m "refactor(agent): remove SessionMode enum"
```

---

### Task 7: Update AgentWorker

**Files:**
- Modify: `src/picklebot/server/agent_worker.py`
- Test: `tests/server/test_agent_worker.py`

**Step 1: Update imports**

Change imports in `src/picklebot/server/agent_worker.py`:

```python
from picklebot.core.agent import Agent
from picklebot.core.events import (
    Event,
    EventType,
    Source,
    InboundEvent,
    OutboundEvent,
    DispatchEvent,
    DispatchResultEvent,
)
```

Remove: `SessionMode` from imports

**Step 2: Update SessionExecutor.__init__**

Modify `src/picklebot/server/agent_worker.py`:

```python
class SessionExecutor:
    """Executes a single agent session from a typed event."""

    def __init__(
        self,
        context: "SharedContext",
        agent_def: "AgentDef",
        event: ProcessableEvent,
        semaphore: asyncio.Semaphore,
    ):
        self.context = context
        self.agent_def = agent_def
        self.event = event
        self.semaphore = semaphore

        # Extract fields from typed event
        self.agent_id = event.agent_id
        self.retry_count = event.retry_count
```

Remove the `self.mode` assignment.

**Step 3: Update SessionExecutor._execute**

Modify `src/picklebot/server/agent_worker.py`:

```python
async def _execute(self) -> None:
    """Run the actual agent session."""
    session_id = self.event.session_id or None

    try:
        agent = Agent(self.agent_def, self.context)

        # Extract source and context from event
        source = self.event.source
        context = self.event.context if isinstance(self.event, InboundEvent) else None

        if session_id:
            try:
                session = agent.resume_session(session_id)
            except ValueError:
                logger.warning(f"Session {session_id} not found, creating new")
                session = agent.new_session(source, context, session_id=session_id)
        else:
            session = agent.new_session(source, context)
            session_id = session.session_id

        response = await session.chat(self.event.content)
        logger.info(f"Session completed: {session_id}")

        # Publish result event based on input type
        if isinstance(self.event, DispatchEvent):
            result_event = DispatchResultEvent(
                session_id=session_id,
                agent_id=self.agent_def.id,
                source=Source.agent(self.agent_def.id),
                content=response,
                timestamp=time.time(),
            )
        else:
            result_event = OutboundEvent(
                session_id=session_id,
                agent_id=self.agent_def.id,
                source=Source.agent(self.agent_def.id),
                content=response,
                timestamp=time.time(),
            )
        await self.context.eventbus.publish(result_event)

    except Exception as e:
        logger.error(f"Session failed: {e}")

        if self.retry_count < MAX_RETRIES:
            retry_event = replace(
                self.event,
                retry_count=self.retry_count + 1,
                content=".",
            )
            await self.context.eventbus.publish(retry_event)
        else:
            if isinstance(self.event, DispatchEvent):
                result_event = DispatchResultEvent(
                    session_id=session_id,
                    agent_id=self.agent_def.id,
                    source=Source.agent(self.agent_def.id),
                    content="",
                    timestamp=time.time(),
                    error=str(e),
                )
            else:
                result_event = OutboundEvent(
                    session_id=session_id,
                    agent_id=self.agent_def.id,
                    source=Source.agent(self.agent_def.id),
                    content="",
                    timestamp=time.time(),
                    error=str(e),
                )
            await self.context.eventbus.publish(result_event)
```

**Step 4: Run tests**

Run: `uv run pytest tests/server/test_agent_worker.py -v`
Expected: PASS (may need test updates)

**Step 5: Commit**

```bash
git add src/picklebot/server/agent_worker.py tests/server/test_agent_worker.py
git commit -m "refactor(agent_worker): use source instead of SessionMode"
```

---

### Task 8: Update MessageBusWorker

**Files:**
- Modify: `src/picklebot/server/messagebus_worker.py`

**Step 1: Update imports**

Change imports in `src/picklebot/server/messagebus_worker.py`:

```python
from picklebot.core.agent import Agent
from picklebot.core.events import InboundEvent, Source
```

Remove: `SessionMode` from imports

**Step 2: Update _get_or_create_session_id**

Modify `src/picklebot/server/messagebus_worker.py`:

```python
def _get_or_create_session_id(self, platform: str, user_id: str) -> str:
    """Get existing session_id or create new session for this user."""
    # CLI has a single session stored in the worker
    if platform == "cli":
        if not self._cli_session_id:
            session = self.agent.new_session(
                source=Source.platform(platform, user_id),
                context=None,  # CLI context created separately
            )
            self._cli_session_id = session.session_id
        return self._cli_session_id

    # Other platforms use typed config
    platform_config = getattr(self.context.config.messagebus, platform, None)
    if platform_config:
        session_id = platform_config.sessions.get(user_id)
        if session_id:
            return session_id

    # No existing session - create new
    session = self.agent.new_session(
        source=Source.platform(platform, user_id),
        context=None,  # Context passed in callback, not stored here
    )
    self.context.config.set_runtime(
        f"messagebus.{platform}.sessions.{user_id}", session.session_id
    )

    return session.session_id
```

**Step 3: Update callback to pass context**

The callback already has access to context. The session creation happens in `_get_or_create_session_id` which doesn't have context. We need to refactor slightly.

Actually, looking at the design, the context should be stored at session creation. Let me update the callback to handle this:

Modify the callback in `_create_callback`:

```python
def _create_callback(self, platform: str):
    """Create callback for a specific platform."""

    async def callback(message: str, context: Any) -> None:
        try:
            bus = self.bus_map[platform]

            if not bus.is_allowed(context):
                self.logger.debug(
                    f"Ignored non-whitelisted message from {platform}"
                )
                return

            # Check for slash command
            if message.startswith("/"):
                self.logger.debug(f"Processing slash command from {platform}")
                result = self.context.command_registry.dispatch(
                    message, self.context
                )
                if result:
                    await bus.reply(result, context)
                return

            # Extract user_id from context
            user_id = context.user_id
            source = Source.platform(platform, user_id)

            # Check for existing session
            session_id = self._get_or_create_session_id(platform, user_id, context)

            # Publish INBOUND event
            event = InboundEvent(
                session_id=session_id,
                agent_id=self.context.config.default_agent,
                source=source,
                content=message,
                timestamp=time.time(),
                context=context,
            )
            await self.context.eventbus.publish(event)
            self.logger.debug(f"Published INBOUND event from {event.source}")

        except Exception as e:
            self.logger.error(f"Error processing message from {platform}: {e}")

    return callback
```

And update `_get_or_create_session_id`:

```python
def _get_or_create_session_id(self, platform: str, user_id: str, context: Any = None) -> str:
    """Get existing session_id or create new session for this user."""
    # CLI has a single session stored in the worker
    if platform == "cli":
        if not self._cli_session_id:
            session = self.agent.new_session(
                source=Source.platform(platform, user_id),
                context=context,
            )
            self._cli_session_id = session.session_id
        return self._cli_session_id

    # Other platforms use typed config
    platform_config = getattr(self.context.config.messagebus, platform, None)
    if platform_config:
        session_id = platform_config.sessions.get(user_id)
        if session_id:
            return session_id

    # No existing session - create new
    session = self.agent.new_session(
        source=Source.platform(platform, user_id),
        context=context,
    )
    self.context.config.set_runtime(
        f"messagebus.{platform}.sessions.{user_id}", session.session_id
    )

    return session.session_id
```

**Step 4: Run tests**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/server/messagebus_worker.py
git commit -m "refactor(messagebus_worker): use source instead of SessionMode"
```

---

### Task 9: Update CronWorker

**Files:**
- Modify: `src/picklebot/server/cron_worker.py`

**Step 1: Update imports**

Change imports in `src/picklebot/server/cron_worker.py`:

```python
from picklebot.core.agent import Agent
from picklebot.core.events import InboundEvent, Source
```

Remove: `SessionMode` from imports

**Step 2: Update cron handler**

Modify `src/picklebot/server/cron_worker.py`:

```python
session = agent.new_session(
    source=Source.cron(cron_id),
    context=None,
)
```

**Step 3: Run tests**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/server/cron_worker.py
git commit -m "refactor(cron_worker): use source instead of SessionMode"
```

---

### Task 10: Update SubagentTool

**Files:**
- Modify: `src/picklebot/tools/subagent_tool.py`

**Step 1: Update imports**

Change imports in `src/picklebot/tools/subagent_tool.py`:

```python
if TYPE_CHECKING:
    from picklebot.core.agent import Agent, AgentSession
```

Remove: `SessionMode` from imports

**Step 2: Remove SessionMode.JOB usage**

The subagent tool creates DispatchEvent which gets processed by AgentWorker. The source is already set on the event. No direct SessionMode usage needed.

Check for any `SessionMode.JOB` references and remove them.

**Step 3: Run tests**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/tools/subagent_tool.py
git commit -m "refactor(subagent_tool): remove SessionMode usage"
```

---

### Task 11: Final Verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run linting**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 3: Manual smoke test**

Run: `uv run picklebot chat -a pickle`
Send a message and verify it works.

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address remaining issues from session source refactor"
```

---

## Summary

This refactor removes `SessionMode` and makes sessions self-describing via their `source` field. The behavior (max_history, tool availability) is derived from source using a simple helper function. Session context (MessageContext) is now persisted, enabling proper reply routing for resumed sessions.
