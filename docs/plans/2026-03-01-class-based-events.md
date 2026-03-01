# Class-Based Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove EventType enum, use event classes directly for subscription routing and serialization.

**Architecture:** EventBus subscribers keyed by `type[Event]` instead of `EventType`. Generic `subscribe()` method enforces handler type matches event class. Serialization uses `__class__.__name__` instead of `type.value`.

**Tech Stack:** Python dataclasses, TypeVar for generics, isinstance checks

---

### Task 1: Add Generic Type Support to EventBus

**Files:**
- Modify: `src/picklebot/core/eventbus.py`
- Test: `tests/core/test_context_eventbus.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_context_eventbus.py`:

```python
import pytest
from picklebot.core.eventbus import EventBus
from picklebot.core.events import InboundEvent, OutboundEvent


class TestEventBusGenericSubscribe:
    """Tests for type-safe generic subscribe."""

    @pytest.fixture
    def event_bus(self, test_context):
        """Create an EventBus for testing."""
        return EventBus(test_context)

    @pytest.mark.asyncio
    async def test_subscribe_by_class_type(self, event_bus):
        """subscribe should accept event class as first argument."""
        received = []

        async def handler(event: InboundEvent) -> None:
            received.append(event)

        event_bus.subscribe(InboundEvent, handler)

        event = InboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="hello",
        )
        await event_bus._notify_subscribers(event)

        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_subscribe_different_classes_independently(self, event_bus):
        """Subscribing to one class should not receive events of another class."""
        inbound_received = []
        outbound_received = []

        async def inbound_handler(event: InboundEvent) -> None:
            inbound_received.append(event)

        async def outbound_handler(event: OutboundEvent) -> None:
            outbound_received.append(event)

        event_bus.subscribe(InboundEvent, inbound_handler)
        event_bus.subscribe(OutboundEvent, outbound_handler)

        inbound = InboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="hello",
        )
        outbound = OutboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="response",
        )

        await event_bus._notify_subscribers(inbound)
        await event_bus._notify_subscribers(outbound)

        assert len(inbound_received) == 1
        assert len(outbound_received) == 1
        assert inbound_received[0] is inbound
        assert outbound_received[0] is outbound

    @pytest.mark.asyncio
    async def test_dispatch_uses_type_event(self, event_bus):
        """_notify_subscribers should use type(event) as key."""
        received = []

        async def handler(event: InboundEvent) -> None:
            received.append(event)

        event_bus.subscribe(InboundEvent, handler)

        event = InboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="hello",
        )
        await event_bus._notify_subscribers(event)

        assert len(received) == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_context_eventbus.py::TestEventBusGenericSubscribe -v`
Expected: FAIL - `TypeError: subscribe() takes 2 positional arguments but 3 were given` or similar

**Step 3: Update EventBus with generic subscribe**

Modify `src/picklebot/core/eventbus.py`:

```python
from typing import Awaitable, Callable, TypeVar

from .events import Event

if TYPE_CHECKING:
    from picklebot.core.context import SharedContext

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]
E = TypeVar("E", bound=Event)


class EventBus(Worker):
    """Central event bus with subscription support and async dispatch."""

    def __init__(self, context: "SharedContext"):
        super().__init__(context)
        self.context = context
        self._subscribers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self.pending_dir = context.config.event_path / "pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def subscribe(
        self, event_class: type[E], handler: Callable[[E], Awaitable[None]]
    ) -> None:
        """Subscribe a handler to an event class.

        Args:
            event_class: The event class to subscribe to (e.g., InboundEvent)
            handler: Async function that handles events of this type
        """
        self._subscribers[event_class].append(handler)  # type: ignore[arg-type]
        logger.debug(f"Subscribed handler to {event_class.__name__} events")

    def unsubscribe(self, handler: Handler) -> None:
        """Remove a handler from all subscriptions."""
        for event_class in self._subscribers:
            if handler in self._subscribers[event_class]:
                self._subscribers[event_class].remove(handler)
                logger.debug(f"Unsubscribed handler from {event_class.__name__} events")

    # ... rest of class unchanged for now
```

**Step 4: Update _notify_subscribers to use type(event)**

In `src/picklebot/core/eventbus.py`:

```python
async def _notify_subscribers(self, event: Event) -> None:
    """Notify all subscribers of an event (waits for all handlers to complete)."""
    handlers = self._subscribers.get(type(event), [])
    if not handlers:
        return

    tasks = [handler(event) for handler in handlers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in event handler: {result}")
```

**Step 5: Remove EventType import**

Remove `EventType` from imports in `src/picklebot/core/eventbus.py`:

```python
from .events import (
    Event,
    deserialize_event,
)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_context_eventbus.py::TestEventBusGenericSubscribe -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/picklebot/core/eventbus.py tests/core/test_context_eventbus.py
git commit -m "feat(eventbus): add generic subscribe by event class"
```

---

### Task 2: Update _persist_outbound to Use isinstance

**Files:**
- Modify: `src/picklebot/core/eventbus.py`
- Test: `tests/events/test_bus.py`

**Step 1: Write the failing test**

Add to `tests/events/test_bus.py`:

```python
class TestEventBusPersistOutbound:
    """Tests for outbound event persistence."""

    @pytest.mark.asyncio
    async def test_persist_outbound_only_persists_outbound_events(self, event_bus):
        """Only OutboundEvent should be persisted."""
        from picklebot.core.events import InboundEvent, OutboundEvent

        # InboundEvent should not be persisted
        inbound = InboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="hello",
        )
        await event_bus._persist_outbound(inbound)

        pending_files = list(event_bus.pending_dir.glob("*.json"))
        assert len(pending_files) == 0

        # OutboundEvent should be persisted
        outbound = OutboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="test",
            content="response",
        )
        await event_bus._persist_outbound(outbound)

        pending_files = list(event_bus.pending_dir.glob("*.json"))
        assert len(pending_files) == 1
```

**Step 2: Update _persist_outbound to use isinstance**

In `src/picklebot/core/eventbus.py`:

```python
async def _persist_outbound(self, event: Event) -> None:
    """Persist event to disk (only OutboundEvent)."""
    from picklebot.core.events import OutboundEvent

    if not isinstance(event, OutboundEvent):
        return

    filename = f"{event.timestamp}_{event.session_id}.json"
    # ... rest unchanged
```

**Step 3: Run tests**

Run: `uv run pytest tests/events/test_bus.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/core/eventbus.py tests/events/test_bus.py
git commit -m "refactor(eventbus): use isinstance for outbound check"
```

---

### Task 3: Remove EventType Enum and event.type Property

**Files:**
- Modify: `src/picklebot/core/events.py`
- Test: `tests/core/test_events.py`

**Step 1: Write the failing tests**

Add to `tests/core/test_events.py`:

```python
class TestEventSerializationWithoutType:
    """Tests for serialization without EventType enum."""

    def test_to_dict_uses_class_name(self):
        """to_dict should use __class__.__name__ for type field."""
        event = InboundEvent(
            session_id="test",
            agent_id="test-agent",
            source="telegram:user_123",
            content="hello",
        )
        data = event.to_dict()

        assert data["type"] == "InboundEvent"

    def test_deserialize_by_class_name(self):
        """deserialize_event should look up by class name."""
        data = {
            "type": "InboundEvent",
            "session_id": "test",
            "agent_id": "test-agent",
            "source": "telegram:user_123",
            "content": "hello",
            "retry_count": 0,
            "context": None,
        }
        event = deserialize_event(data)

        assert isinstance(event, InboundEvent)
        assert event.session_id == "test"

    def test_deserialize_outbound_event(self):
        """deserialize_event should handle OutboundEvent."""
        data = {
            "type": "OutboundEvent",
            "session_id": "test",
            "agent_id": "test-agent",
            "source": "agent:cookie",
            "content": "response",
            "error": None,
        }
        event = deserialize_event(data)

        assert isinstance(event, OutboundEvent)

    def test_deserialize_dispatch_event(self):
        """deserialize_event should handle DispatchEvent."""
        data = {
            "type": "DispatchEvent",
            "session_id": "test",
            "agent_id": "test-agent",
            "source": "agent:cookie",
            "content": "do something",
            "parent_session_id": "parent-123",
            "retry_count": 0,
        }
        event = deserialize_event(data)

        assert isinstance(event, DispatchEvent)
        assert event.parent_session_id == "parent-123"

    def test_deserialize_dispatch_result_event(self):
        """deserialize_event should handle DispatchResultEvent."""
        data = {
            "type": "DispatchResultEvent",
            "session_id": "test",
            "agent_id": "test-agent",
            "source": "agent:cookie",
            "content": "result",
            "error": None,
        }
        event = deserialize_event(data)

        assert isinstance(event, DispatchResultEvent)

    def test_deserialize_unknown_type_raises(self):
        """deserialize_event should raise for unknown type."""
        data = {
            "type": "UnknownEvent",
            "session_id": "test",
            "agent_id": "test-agent",
            "source": "test",
            "content": "hello",
        }

        with pytest.raises(ValueError, match="Unknown event type"):
            deserialize_event(data)
```

**Step 2: Update events.py - remove EventType and type properties**

Modify `src/picklebot/core/events.py`:

```python
"""Event types and data classes for the event bus."""

import time
from dataclasses import dataclass, field
from typing import Any

from picklebot.messagebus.base import MessageContext


class Source:
    """Factory for creating typed event sources."""

    @staticmethod
    def agent(agent_id: str) -> str:
        return f"agent:{agent_id}"

    @staticmethod
    def platform(platform: str, user_id: str) -> str:
        return f"{platform}:{user_id}"

    @staticmethod
    def cron(cron_id: str) -> str:
        return f"cron:{cron_id}"


def _serialize_context(context: MessageContext | None) -> dict[str, Any]:
    """Serialize a MessageContext to a dictionary."""
    if context is None:
        return {}

    context_type = type(context).__name__

    if hasattr(context, "__dataclass_fields__"):
        data = {}
        for field_name in context.__dataclass_fields__:
            data[field_name] = getattr(context, field_name)
        return {"type": context_type, "data": data}

    return {"type": context_type, "data": {}}


def _deserialize_context(data: dict[str, Any] | None) -> MessageContext | None:
    """Deserialize a dictionary back to a MessageContext."""
    if not data:
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


@dataclass
class Event:
    """Base class for all typed events."""

    session_id: str
    agent_id: str
    source: str
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary, including type."""
        result: dict[str, Any] = {"type": self.__class__.__name__}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if field_name == "context":
                result[field_name] = _serialize_context(value)
            else:
                result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize event from dictionary, excluding type field."""
        kwargs = {}
        for k, v in data.items():
            if k == "type":
                continue
            if k == "context":
                kwargs[k] = _deserialize_context(v)
            elif k in cls.__dataclass_fields__:
                kwargs[k] = v

        return cls(**kwargs)


@dataclass
class InboundEvent(Event):
    """Event for external work entering the system (platforms, cron, retry)."""

    retry_count: int = 0
    context: MessageContext | None = None


@dataclass
class OutboundEvent(Event):
    """Event for agent responses to deliver to platforms."""

    error: str | None = None


@dataclass
class DispatchEvent(Event):
    """Event for internal agent-to-agent delegation."""

    parent_session_id: str = ""
    retry_count: int = 0


@dataclass
class DispatchResultEvent(Event):
    """Event for result of a dispatched job."""

    error: str | None = None


# Registry mapping class names to event classes
_EVENT_CLASSES: dict[str, type[Event]] = {
    "InboundEvent": InboundEvent,
    "OutboundEvent": OutboundEvent,
    "DispatchEvent": DispatchEvent,
    "DispatchResultEvent": DispatchResultEvent,
}


def serialize_event(event: Event) -> dict[str, Any]:
    """Serialize any event type to dict."""
    return event.to_dict()


def deserialize_event(data: dict[str, Any]) -> Event:
    """Deserialize dict to appropriate event type."""
    event_type: str = data.get("type")

    event_class = _EVENT_CLASSES.get(event_type)
    if event_class is None:
        raise ValueError(f"Unknown event type: {event_type}")

    return event_class.from_dict(data)
```

**Step 3: Run tests**

Run: `uv run pytest tests/core/test_events.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/picklebot/core/events.py tests/core/test_events.py
git commit -m "refactor(events): remove EventType enum, use class name for serialization"
```

---

### Task 4: Update All EventType References

**Files:**
- Modify: `src/picklebot/server/agent_worker.py`
- Modify: `src/picklebot/server/delivery_worker.py`
- Test: Run all tests

**Step 1: Find all EventType references**

Run: `grep -r "EventType" src/`

**Step 2: Update agent_worker.py**

In `src/picklebot/server/agent_worker.py`, remove `EventType` from imports:

```python
from picklebot.core.events import (
    Event,
    Source,
    InboundEvent,
    OutboundEvent,
    DispatchEvent,
    DispatchResultEvent,
)
```

Update subscribe calls:

```python
# In __init__
self.context.eventbus.subscribe(InboundEvent, self._dispatch_event)
self.context.eventbus.subscribe(DispatchEvent, self._dispatch_event)
self.logger.info("AgentWorker subscribed to InboundEvent and DispatchEvent events")
```

**Step 3: Update delivery_worker.py**

In `src/picklebot/server/delivery_worker.py`, update imports and subscribe:

```python
from picklebot.core.events import Event, OutboundEvent

# In __init__
self.context.eventbus.subscribe(OutboundEvent, self.handle_outbound)
self.logger.info("DeliveryWorker subscribed to OutboundEvent events")
```

**Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/picklebot/server/agent_worker.py src/picklebot/server/delivery_worker.py
git commit -m "refactor(workers): update to use class-based event subscription"
```

---

### Task 5: Final Verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 2: Run linting**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 3: Verify no EventType references remain**

Run: `grep -r "EventType" src/`
Expected: No matches

**Step 4: Commit any remaining fixes**

```bash
git add -A
git commit -m "fix: address remaining issues from class-based events refactor"
```

---

## Summary

This refactor removes the `EventType` enum and uses event classes directly for:
- Subscription routing (key by `type[Event]`)
- Serialization (use `__class__.__name__`)
- Type checking (use `isinstance`)

The generic `subscribe()` method provides compile-time type safety for handlers.
