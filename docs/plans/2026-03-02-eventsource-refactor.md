# EventSource Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace string `source` + `context` with typed `EventSource` hierarchy, deprecating Context entirely.

**Architecture:** EventSource is an ABC with auto-registration via `__init_subclass__`. Platform-specific subclasses (TelegramEventSource, etc.) live in their respective messagebus modules. Each subclass serializes via `__str__` and deserializes via `from_string()`. Events use typed EventSource instead of string + context.

**Tech Stack:** Python dataclasses, ABC, ClassVar, pytest

---

## Task 1: Add EventSource ABC to core/events.py

**Files:**
- Modify: `src/picklebot/core/events.py`
- Test: `tests/events/test_source.py`

**Step 1: Write the failing test**

Create `tests/events/test_source.py`:

```python
"""Tests for EventSource hierarchy."""

import pytest
from picklebot.core.events import EventSource


class TestEventSourceBase:
    """Tests for EventSource ABC behavior."""

    def test_cannot_instantiate_abstract_base(self):
        """EventSource should not be directly instantiable."""
        with pytest.raises(TypeError):
            EventSource()

    def test_from_string_raises_on_unknown_namespace(self):
        """from_string should raise for unregistered namespace."""
        with pytest.raises(ValueError, match="Unknown source namespace"):
            EventSource.from_string("unknown:value")


class TestAgentEventSource:
    """Tests for AgentEventSource."""

    def test_string_roundtrip(self):
        """Agent source should serialize and deserialize correctly."""
        from picklebot.core.events import AgentEventSource

        original = AgentEventSource(agent_id="pickle")
        serialized = str(original)
        deserialized = AgentEventSource.from_string(serialized)

        assert serialized == "agent:pickle"
        assert deserialized.agent_id == "pickle"

    def test_type_properties(self):
        """Agent source should have correct type properties."""
        from picklebot.core.events import AgentEventSource

        source = AgentEventSource(agent_id="pickle")
        assert source.is_agent is True
        assert source.is_platform is False
        assert source.is_cron is False
        assert source.platform_name is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_source.py -v`
Expected: FAIL with import errors or TypeError

**Step 3: Add EventSource ABC and AgentEventSource**

Modify `src/picklebot/core/events.py` - add after the imports, before `Source` class:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class EventSource(ABC):
    """Abstract base for all event sources.

    Subclasses define _namespace for registry lookup and implement
    serialization via __str__ and from_string.
    """

    _registry: dict[str, type["EventSource"]] = {}
    _namespace: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls._namespace:
            cls._registry[cls._namespace] = cls

    @property
    def is_platform(self) -> bool:
        return self._namespace.startswith("platform-")

    @property
    def is_agent(self) -> bool:
        return self._namespace == "agent"

    @property
    def is_cron(self) -> bool:
        return self._namespace == "cron"

    @property
    def platform_name(self) -> str | None:
        if not self.is_platform:
            return None
        return self._namespace.split("-", 1)[1]

    @classmethod
    def from_string(cls, s: str) -> "EventSource":
        """Parse string to EventSource using namespace registry."""
        namespace = s.split(":")[0]
        source_cls = cls._registry.get(namespace)
        if not source_cls:
            raise ValueError(f"Unknown source namespace: {namespace}")
        return source_cls.from_string(s)

    @abstractmethod
    def __str__(self) -> str: ...

    @classmethod
    @abstractmethod
    def from_string(cls, s: str) -> "EventSource": ...


@dataclass
class AgentEventSource(EventSource):
    """Source for agent-generated events."""

    _namespace = "agent"
    agent_id: str

    def __str__(self) -> str:
        return f"agent:{self.agent_id}"

    @classmethod
    def from_string(cls, s: str) -> "AgentEventSource":
        _, agent_id = s.split(":", 1)
        return cls(agent_id=agent_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_source.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/events.py tests/events/test_source.py
git commit -m "feat(events): add EventSource ABC and AgentEventSource"
```

---

## Task 2: Add CronEventSource

**Files:**
- Modify: `src/picklebot/core/events.py`
- Modify: `tests/events/test_source.py`

**Step 1: Write the failing test**

Add to `tests/events/test_source.py`:

```python
class TestCronEventSource:
    """Tests for CronEventSource."""

    def test_string_roundtrip(self):
        """Cron source should serialize and deserialize correctly."""
        from picklebot.core.events import CronEventSource

        original = CronEventSource(cron_id="daily-summary")
        serialized = str(original)
        deserialized = CronEventSource.from_string(serialized)

        assert serialized == "cron:daily-summary"
        assert deserialized.cron_id == "daily-summary"

    def test_type_properties(self):
        """Cron source should have correct type properties."""
        from picklebot.core.events import CronEventSource

        source = CronEventSource(cron_id="daily-summary")
        assert source.is_cron is True
        assert source.is_agent is False
        assert source.is_platform is False
        assert source.platform_name is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_source.py::TestCronEventSource -v`
Expected: FAIL with ImportError

**Step 3: Add CronEventSource**

Add to `src/picklebot/core/events.py` after AgentEventSource:

```python
@dataclass
class CronEventSource(EventSource):
    """Source for cron-triggered events."""

    _namespace = "cron"
    cron_id: str

    def __str__(self) -> str:
        return f"cron:{self.cron_id}"

    @classmethod
    def from_string(cls, s: str) -> "CronEventSource":
        _, cron_id = s.split(":", 1)
        return cls(cron_id=cron_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_source.py::TestCronEventSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/events.py tests/events/test_source.py
git commit -m "feat(events): add CronEventSource"
```

---

## Task 3: Add TelegramEventSource

**Files:**
- Modify: `src/picklebot/messagebus/telegram_bus.py`
- Modify: `tests/events/test_source.py`

**Step 1: Write the failing test**

Add to `tests/events/test_source.py`:

```python
class TestTelegramEventSource:
    """Tests for TelegramEventSource."""

    def test_string_roundtrip(self):
        """Telegram source should serialize and deserialize correctly."""
        from picklebot.messagebus.telegram_bus import TelegramEventSource

        original = TelegramEventSource(user_id="12345", chat_id="67890")
        serialized = str(original)
        deserialized = TelegramEventSource.from_string(serialized)

        assert serialized == "platform-telegram:12345:67890"
        assert deserialized.user_id == "12345"
        assert deserialized.chat_id == "67890"

    def test_type_properties(self):
        """Telegram source should have correct type properties."""
        from picklebot.messagebus.telegram_bus import TelegramEventSource

        source = TelegramEventSource(user_id="12345", chat_id="67890")
        assert source.is_platform is True
        assert source.is_agent is False
        assert source.is_cron is False
        assert source.platform_name == "telegram"

    def test_via_base_from_string(self):
        """Telegram source should be parseable via EventSource.from_string."""
        from picklebot.core.events import EventSource
        from picklebot.messagebus.telegram_bus import TelegramEventSource

        source = EventSource.from_string("platform-telegram:12345:67890")
        assert isinstance(source, TelegramEventSource)
        assert source.user_id == "12345"
        assert source.chat_id == "67890"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_source.py::TestTelegramEventSource -v`
Expected: FAIL with ImportError

**Step 3: Add TelegramEventSource**

Modify `src/picklebot/messagebus/telegram_bus.py` - add import and class after existing imports:

```python
from dataclasses import dataclass
from typing import ClassVar

from picklebot.core.events import EventSource


@dataclass
class TelegramEventSource(EventSource):
    """Source for Telegram-originated events."""

    _namespace = "platform-telegram"
    user_id: str
    chat_id: str

    def __str__(self) -> str:
        return f"platform-telegram:{self.user_id}:{self.chat_id}"

    @classmethod
    def from_string(cls, s: str) -> "TelegramEventSource":
        _, user_id, chat_id = s.split(":")
        return cls(user_id=user_id, chat_id=chat_id)

    @property
    def platform_name(self) -> str:
        return "telegram"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_source.py::TestTelegramEventSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/messagebus/telegram_bus.py tests/events/test_source.py
git commit -m "feat(telegram): add TelegramEventSource"
```

---

## Task 4: Add DiscordEventSource

**Files:**
- Modify: `src/picklebot/messagebus/discord_bus.py`
- Modify: `tests/events/test_source.py`

**Step 1: Write the failing test**

Add to `tests/events/test_source.py`:

```python
class TestDiscordEventSource:
    """Tests for DiscordEventSource."""

    def test_string_roundtrip(self):
        """Discord source should serialize and deserialize correctly."""
        from picklebot.messagebus.discord_bus import DiscordEventSource

        original = DiscordEventSource(user_id="12345", channel_id="67890")
        serialized = str(original)
        deserialized = DiscordEventSource.from_string(serialized)

        assert serialized == "platform-discord:12345:67890"
        assert deserialized.user_id == "12345"
        assert deserialized.channel_id == "67890"

    def test_type_properties(self):
        """Discord source should have correct type properties."""
        from picklebot.messagebus.discord_bus import DiscordEventSource

        source = DiscordEventSource(user_id="12345", channel_id="67890")
        assert source.is_platform is True
        assert source.platform_name == "discord"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_source.py::TestDiscordEventSource -v`
Expected: FAIL with ImportError

**Step 3: Add DiscordEventSource**

Modify `src/picklebot/messagebus/discord_bus.py` - add after existing imports:

```python
from dataclasses import dataclass

from picklebot.core.events import EventSource


@dataclass
class DiscordEventSource(EventSource):
    """Source for Discord-originated events."""

    _namespace = "platform-discord"
    user_id: str
    channel_id: str

    def __str__(self) -> str:
        return f"platform-discord:{self.user_id}:{self.channel_id}"

    @classmethod
    def from_string(cls, s: str) -> "DiscordEventSource":
        _, user_id, channel_id = s.split(":")
        return cls(user_id=user_id, channel_id=channel_id)

    @property
    def platform_name(self) -> str:
        return "discord"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_source.py::TestDiscordEventSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/messagebus/discord_bus.py tests/events/test_source.py
git commit -m "feat(discord): add DiscordEventSource"
```

---

## Task 5: Add CliEventSource

**Files:**
- Modify: `src/picklebot/messagebus/cli_bus.py`
- Modify: `tests/events/test_source.py`

**Step 1: Write the failing test**

Add to `tests/events/test_source.py`:

```python
class TestCliEventSource:
    """Tests for CliEventSource."""

    def test_string_roundtrip(self):
        """CLI source should serialize and deserialize correctly."""
        from picklebot.messagebus.cli_bus import CliEventSource

        original = CliEventSource(user_id="default")
        serialized = str(original)
        deserialized = CliEventSource.from_string(serialized)

        assert serialized == "platform-cli:default"
        assert deserialized.user_id == "default"

    def test_type_properties(self):
        """CLI source should have correct type properties."""
        from picklebot.messagebus.cli_bus import CliEventSource

        source = CliEventSource(user_id="default")
        assert source.is_platform is True
        assert source.platform_name == "cli"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_source.py::TestCliEventSource -v`
Expected: FAIL with ImportError

**Step 3: Add CliEventSource**

Modify `src/picklebot/messagebus/cli_bus.py` - add after existing imports:

```python
from dataclasses import dataclass

from picklebot.core.events import EventSource


@dataclass
class CliEventSource(EventSource):
    """Source for CLI-originated events."""

    _namespace = "platform-cli"
    user_id: str

    def __str__(self) -> str:
        return f"platform-cli:{self.user_id}"

    @classmethod
    def from_string(cls, s: str) -> "CliEventSource":
        _, user_id = s.split(":", 1)
        return cls(user_id=user_id)

    @property
    def platform_name(self) -> str:
        return "cli"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_source.py::TestCliEventSource -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/messagebus/cli_bus.py tests/events/test_source.py
git commit -m "feat(cli): add CliEventSource"
```

---

## Task 6: Update Event classes to use typed EventSource

**Files:**
- Modify: `src/picklebot/core/events.py`
- Modify: `tests/events/test_types.py`

**Step 1: Write the failing test**

Check existing tests and add serialization test to `tests/events/test_types.py`:

```python
class TestEventSourceSerialization:
    """Tests for EventSource serialization in events."""

    def test_inbound_event_with_agent_source(self):
        """InboundEvent should serialize/deserialize with AgentEventSource."""
        from picklebot.core.events import InboundEvent, AgentEventSource

        source = AgentEventSource(agent_id="pickle")
        event = InboundEvent(
            session_id="sess-1",
            agent_id="pickle",
            source=source,
            content="hello",
        )

        data = event.to_dict()
        assert data["source"] == "agent:pickle"

        restored = InboundEvent.from_dict(data)
        assert isinstance(restored.source, AgentEventSource)
        assert restored.source.agent_id == "pickle"

    def test_inbound_event_with_platform_source(self):
        """InboundEvent should serialize/deserialize with platform sources."""
        from picklebot.core.events import InboundEvent
        from picklebot.messagebus.telegram_bus import TelegramEventSource

        source = TelegramEventSource(user_id="123", chat_id="456")
        event = InboundEvent(
            session_id="sess-1",
            agent_id="pickle",
            source=source,
            content="hello",
        )

        data = event.to_dict()
        assert data["source"] == "platform-telegram:123:456"

        restored = InboundEvent.from_dict(data)
        assert isinstance(restored.source, TelegramEventSource)
        assert restored.source.user_id == "123"
        assert restored.source.chat_id == "456"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_types.py::TestEventSourceSerialization -v`
Expected: FAIL with type errors (source is currently str)

**Step 3: Update Event base class**

Modify `src/picklebot/core/events.py`:

1. Change `Event.source` type from `str` to `EventSource`
2. Update `to_dict()` to serialize source via `str()`
3. Update `from_dict()` to deserialize via `EventSource.from_string()`

```python
@dataclass
class Event:
    """Base class for all typed events."""

    session_id: str
    agent_id: str
    source: EventSource  # Changed from str
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary, including type."""
        result: dict[str, Any] = {"type": self.__class__.__name__}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if field_name == "source":
                result[field_name] = str(value)  # Serialize via __str__
            elif field_name == "context":
                result[field_name] = _serialize_context(value)
            else:
                result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize event from dictionary."""
        kwargs = {}
        for k, v in data.items():
            if k == "type":
                continue
            if k == "source":
                kwargs[k] = EventSource.from_string(v)  # Deserialize
            elif k == "context":
                kwargs[k] = _deserialize_context(v)
            elif k in cls.__dataclass_fields__:
                kwargs[k] = v
        return cls(**kwargs)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_types.py::TestEventSourceSerialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/events.py tests/events/test_types.py
git commit -m "feat(events): update Event to use typed EventSource"
```

---

## Task 7: Remove context field from InboundEvent

**Files:**
- Modify: `src/picklebot/core/events.py`
- Modify: `tests/events/test_types.py`

**Step 1: Write the failing test**

Add to `tests/events/test_types.py`:

```python
def test_inbound_event_no_context_field():
    """InboundEvent should not have context field after refactor."""
    from picklebot.core.events import InboundEvent, AgentEventSource

    source = AgentEventSource(agent_id="pickle")
    event = InboundEvent(
        session_id="sess-1",
        agent_id="pickle",
        source=source,
        content="hello",
    )

    # Should not have context attribute
    assert not hasattr(event, "context")

    # Serialization should not include context
    data = event.to_dict()
    assert "context" not in data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/events/test_types.py::test_inbound_event_no_context_field -v`
Expected: FAIL (context field still exists)

**Step 3: Remove context from InboundEvent**

Modify `src/picklebot/core/events.py`:

```python
@dataclass
class InboundEvent(Event):
    """Event for external work entering the system (platforms, cron, retry)."""

    retry_count: int = 0
    # context field removed - source now carries all data
```

Also remove the context handling from `to_dict()` and `from_dict()` in Event class.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/events/test_types.py::test_inbound_event_no_context_field -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/events.py tests/events/test_types.py
git commit -m "refactor(events): remove context field from InboundEvent"
```

---

## Task 8: Update TelegramBus to use TelegramEventSource

**Files:**
- Modify: `src/picklebot/messagebus/telegram_bus.py`
- Modify: `tests/messagebus/test_telegram_bus.py`

**Step 1: Write the failing test**

Add/update in `tests/messagebus/test_telegram_bus.py`:

```python
def test_reply_uses_event_source():
    """TelegramBus.reply should accept TelegramEventSource instead of context."""
    from picklebot.messagebus.telegram_bus import TelegramEventSource

    # This test verifies the signature change
    # Actual integration test would mock the bot
    source = TelegramEventSource(user_id="123", chat_id="456")
    assert source.chat_id == "456"
```

**Step 2: Run test to verify current state**

Run: `uv run pytest tests/messagebus/test_telegram_bus.py -v`
Expected: Tests may fail due to signature changes

**Step 3: Update TelegramBus**

Modify `src/picklebot/messagebus/telegram_bus.py`:

1. Remove `TelegramContext` class
2. Update `reply()` signature to use `TelegramEventSource`

```python
async def reply(self, content: str, source: TelegramEventSource) -> None:
    """Reply to incoming message."""
    if not self.application:
        raise RuntimeError("TelegramBus not started")

    try:
        await self.application.bot.send_message(
            chat_id=int(source.chat_id), text=content
        )
        logger.debug(f"Sent Telegram reply to {source.chat_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram reply: {e}")
        raise
```

Update `run()` callback to create `TelegramEventSource`:

```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        update.message
        and update.message.text
        and update.effective_chat
        and update.message.from_user
    ):
        user_id = str(update.message.from_user.id)
        chat_id = str(update.effective_chat.id)
        message = update.message.text

        logger.info(
            f"Received Telegram message from user {user_id} in chat {chat_id}"
        )

        ctx = TelegramEventSource(user_id=user_id, chat_id=chat_id)
        try:
            await on_message(message, ctx)
        except Exception as e:
            logger.error(f"Error in message callback: {e}")
```

Also update `is_allowed()`:

```python
def is_allowed(self, source: TelegramEventSource) -> bool:
    """Check if sender is whitelisted."""
    if not self.config.allowed_user_ids:
        return True
    return source.user_id in self.config.allowed_user_ids
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/messagebus/test_telegram_bus.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/messagebus/telegram_bus.py tests/messagebus/test_telegram_bus.py
git commit -m "refactor(telegram): use TelegramEventSource, remove TelegramContext"
```

---

## Task 9: Update DiscordBus to use DiscordEventSource

**Files:**
- Modify: `src/picklebot/messagebus/discord_bus.py`
- Modify: `tests/messagebus/test_discord_bus.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/messagebus/test_discord_bus.py -v`
Expected: May fail due to signature changes

**Step 2: Update DiscordBus**

Same pattern as TelegramBus:
1. Remove `DiscordContext` class
2. Update `reply()`, `is_allowed()`, and `run()` to use `DiscordEventSource`

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/messagebus/test_discord_bus.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/messagebus/discord_bus.py tests/messagebus/test_discord_bus.py
git commit -m "refactor(discord): use DiscordEventSource, remove DiscordContext"
```

---

## Task 10: Update CliBus to use CliEventSource

**Files:**
- Modify: `src/picklebot/messagebus/cli_bus.py`
- Test: `tests/messagebus/test_cli_bus.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/messagebus/test_cli_bus.py -v`

**Step 2: Update CliBus**

Same pattern:
1. Remove `CliContext` class
2. Update methods to use `CliEventSource`

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/messagebus/test_cli_bus.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/messagebus/cli_bus.py tests/messagebus/test_cli_bus.py
git commit -m "refactor(cli): use CliEventSource, remove CliContext"
```

---

## Task 11: Update MessageBusWorker

**Files:**
- Modify: `src/picklebot/server/messagebus_worker.py`
- Test: `tests/server/test_messagebus_worker.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/server/test_messagebus_worker.py -v`

**Step 2: Update MessageBusWorker callback**

Modify `_create_callback()` to create typed sources:

```python
async def callback(message: str, context: Any) -> None:
    try:
        bus = self.bus_map[platform]

        if not bus.is_allowed(context):
            self.logger.debug(f"Ignored non-whitelisted message from {platform}")
            return

        # Check for slash command
        if message.startswith("/"):
            self.logger.debug(f"Processing slash command from {platform}")
            result = self.context.command_registry.dispatch(message, self.context)
            if result:
                return await bus.reply(result, context)

        # context is now the typed EventSource (e.g., TelegramEventSource)
        source = context
        source_str = str(source)  # For routing and session lookup
        agent_id = self.context.routing_table.resolve(source_str)

        if not agent_id:
            self.logger.debug(f"No routing match for {source_str}")
            return

        session_id = self._get_or_create_session_id(source_str, agent_id)

        # Publish INBOUND event with typed source
        event = InboundEvent(
            session_id=session_id,
            agent_id=agent_id,
            source=source,  # Typed EventSource
            content=message,
            timestamp=time.time(),
        )
        await self.context.eventbus.publish(event)
        self.logger.debug(f"Published INBOUND event from {source_str}")

    except Exception as e:
        self.logger.error(f"Error processing message from {platform}: {e}")
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/server/test_messagebus_worker.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/server/messagebus_worker.py tests/server/test_messagebus_worker.py
git commit -m "refactor(messagebus-worker): use typed EventSource for events"
```

---

## Task 12: Update DeliveryWorker

**Files:**
- Modify: `src/picklebot/server/delivery_worker.py`
- Test: `tests/server/test_delivery_worker.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/server/test_delivery_worker.py -v`

**Step 2: Update DeliveryWorker**

Remove `_build_context()` method and use source directly:

```python
async def handle_event(self, event: OutboundEvent) -> None:
    """Handle an outbound message event."""
    try:
        session_info = self._get_session_source(event.session_id)

        if not session_info or not session_info.source:
            self.logger.warning(
                f"No source for session {event.session_id}, skipping delivery"
            )
            return

        # Parse source from string
        source = EventSource.from_string(session_info.source)

        # Get platform from source
        if not source.is_platform:
            self.logger.warning(
                f"Source {source} is not a platform source, skipping delivery"
            )
            return

        platform = source.platform_name
        limit = PLATFORM_LIMITS.get(platform, float("inf"))
        if limit != float("inf"):
            limit = int(limit)
        chunks = chunk_message(
            event.content,
            int(limit) if limit != float("inf") else len(event.content),
        )

        bus = self._get_bus(platform)
        if bus:
            for chunk in chunks:
                await bus.reply(chunk, source)  # Pass source directly

        self.context.eventbus.ack(event)
        self.logger.info(
            f"Delivered message to {platform} for session {event.session_id}"
        )

    except Exception as e:
        self.logger.error(f"Failed to deliver message: {e}")
```

Remove `_build_context()` method entirely.

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/server/test_delivery_worker.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/server/delivery_worker.py tests/server/test_delivery_worker.py
git commit -m "refactor(delivery-worker): use EventSource directly, remove _build_context"
```

---

## Task 13: Update CronWorker

**Files:**
- Modify: `src/picklebot/server/cron_worker.py`
- Test: `tests/server/test_cron_worker.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/server/test_cron_worker.py -v`

**Step 2: Update CronWorker to use CronEventSource**

```python
from picklebot.core.events import InboundEvent, CronEventSource

# In the method that creates events:
source = CronEventSource(cron_id=cron_id)
event = InboundEvent(
    session_id=session_id,
    agent_id=agent_id,
    source=source,
    content=content,
)
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/server/test_cron_worker.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/server/cron_worker.py tests/server/test_cron_worker.py
git commit -m "refactor(cron-worker): use CronEventSource for events"
```

---

## Task 14: Update AgentWorker

**Files:**
- Modify: `src/picklebot/server/agent_worker.py`
- Test: `tests/server/test_agent_worker.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/server/test_agent_worker.py -v`

**Step 2: Update AgentWorker**

Use `AgentEventSource` for any dispatch result events or agent-generated sources.

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/server/test_agent_worker.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/server/agent_worker.py tests/server/test_agent_worker.py
git commit -m "refactor(agent-worker): use AgentEventSource"
```

---

## Task 15: Update SubagentTool

**Files:**
- Modify: `src/picklebot/tools/subagent_tool.py`
- Test: `tests/tools/test_subagent_tool.py`

**Step 1: Run existing tests**

Run: `uv run pytest tests/tools/test_subagent_tool.py -v`

**Step 2: Update SubagentTool**

Use `AgentEventSource` for dispatch events:

```python
from picklebot.core.events import AgentEventSource, DispatchEvent

# When creating dispatch events:
source = AgentEventSource(agent_id=parent_agent_id)
event = DispatchEvent(
    session_id=session_id,
    agent_id=target_agent_id,
    source=source,
    content=task,
    parent_session_id=parent_session_id,
)
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_subagent_tool.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/tools/subagent_tool.py tests/tools/test_subagent_tool.py
git commit -m "refactor(subagent-tool): use AgentEventSource"
```

---

## Task 16: Remove MessageContext ABC and helpers

**Files:**
- Modify: `src/picklebot/messagebus/base.py`
- Modify: `src/picklebot/core/events.py`

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests should pass

**Step 2: Remove MessageContext from base.py**

Remove `MessageContext` class and update `MessageBus` generic type:

```python
from typing import Callable, Awaitable, Any

from picklebot.utils.config import Config


class MessageBus(ABC):
    """Abstract base for messaging platforms."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        pass

    @abstractmethod
    async def run(self, on_message: Callable[[str, Any], Awaitable[None]]) -> None:
        pass

    @abstractmethod
    def is_allowed(self, source: Any) -> bool:
        pass

    @abstractmethod
    async def reply(self, content: str, source: Any) -> None:
        pass

    # ... rest unchanged
```

**Step 3: Remove context helpers from events.py**

Remove `_serialize_context()` and `_deserialize_context()` functions.

Remove old `Source` factory class if still present.

**Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/picklebot/messagebus/base.py src/picklebot/core/events.py
git commit -m "refactor: remove MessageContext ABC and context helpers"
```

---

## Task 17: Fix any remaining tests and lint

**Files:**
- Various test files

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

**Step 2: Fix any failing tests**

Address any remaining tests that reference old context or string source patterns.

**Step 3: Run lint and format**

Run: `uv run black . && uv run ruff check .`

**Step 4: Commit fixes**

```bash
git add .
git commit -m "fix: update remaining tests for EventSource refactor"
```

---

## Task 18: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 2: Verify no Context references remain**

Run: `grep -r "MessageContext" src/`
Expected: No matches (or only in comments)

Run: `grep -r "TelegramContext\|DiscordContext\|CliContext" src/`
Expected: No matches

**Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete EventSource refactor, deprecate Context"
```
