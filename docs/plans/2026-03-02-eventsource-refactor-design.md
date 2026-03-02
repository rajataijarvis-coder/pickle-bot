# EventSource Refactor Design

**Date:** 2026-03-02
**Status:** Approved

## Goal

Replace string `source` + `context` with typed `EventSource` hierarchy, deprecate Context entirely.

## Motivation

- Source and Context duplicate data (both carry `user_id`)
- Context serialization/deserialization is complex
- DeliveryWorker rebuilds context from session anyway
- Typed sources provide cleaner API and better type safety

## Design

### EventSource Base Class (`core/events.py`)

```python
class EventSource(ABC):
    """Abstract base for all event sources."""

    _registry: dict[str, type["EventSource"]] = {}
    _namespace: ClassVar[str] = ""  # Each subclass defines this

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
```

### Subclass Pattern

Each subclass:
- Defines `_namespace` classvar for registry lookup
- Implements `__str__()` for serialization
- Implements `from_string()` classmethod for deserialization
- Uses `@dataclass` for field storage

**AgentEventSource** (in `server/agent_worker.py`):

```python
@dataclass
class AgentEventSource(EventSource):
    _namespace = "agent"
    agent_id: str

    def __str__(self) -> str:
        return f"agent:{self.agent_id}"

    @classmethod
    def from_string(cls, s: str) -> "AgentEventSource":
        _, agent_id = s.split(":", 1)
        return cls(agent_id=agent_id)
```

**CronEventSource** (in `server/cron_worker.py`):

```python
@dataclass
class CronEventSource(EventSource):
    _namespace = "cron"
    cron_id: str

    def __str__(self) -> str:
        return f"cron:{self.cron_id}"

    @classmethod
    def from_string(cls, s: str) -> "CronEventSource":
        _, cron_id = s.split(":", 1)
        return cls(cron_id=cron_id)
```

**TelegramEventSource** (in `messagebus/telegram_bus.py`):

```python
@dataclass
class TelegramEventSource(EventSource):
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

**DiscordEventSource** (in `messagebus/discord_bus.py`):

```python
@dataclass
class DiscordEventSource(EventSource):
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

**CliEventSource** (in `messagebus/cli_bus.py`):

```python
@dataclass
class CliEventSource(EventSource):
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

### String Format

| Source Type | Format | Example |
|-------------|--------|---------|
| Agent | `agent:{agent_id}` | `agent:pickle` |
| Cron | `cron:{cron_id}` | `cron:daily-summary` |
| Telegram | `platform-telegram:{user_id}:{chat_id}` | `platform-telegram:12345:67890` |
| Discord | `platform-discord:{user_id}:{channel_id}` | `platform-discord:12345:67890` |
| CLI | `platform-cli:{user_id}` | `platform-cli:default` |

### Event Changes

**Before:**
```python
@dataclass
class InboundEvent(Event):
    session_id: str
    agent_id: str
    source: str  # Plain string
    content: str
    retry_count: int = 0
    context: MessageContext | None = None  # Separate context
```

**After:**
```python
@dataclass
class InboundEvent(Event):
    session_id: str
    agent_id: str
    source: EventSource  # Typed source with all data
    content: str
    retry_count: int = 0
    # context removed
```

### Serialization

Events serialize/deserialize source via the registry:

```python
# to_dict
result["source"] = str(self.source)

# from_dict
kwargs["source"] = EventSource.from_string(data["source"])
```

### Deleted Code

- `MessageContext` ABC (`messagebus/base.py`)
- `TelegramContext`, `DiscordContext`, `CliContext`
- `_serialize_context()` and `_deserialize_context()` helpers (`core/events.py`)
- Current `Source` factory class (`core/events.py`)

### Worker Changes

**MessageBusWorker:**
```python
# Before
source = f"{platform}:{user_id}"
event = InboundEvent(..., source=source, context=context)

# After
source = TelegramEventSource(user_id=user_id, chat_id=chat_id)
event = InboundEvent(..., source=source)
```

**DeliveryWorker:**
```python
# Before
platform, user_id = session_info.source.split(":", 1)
context = self._build_context(platform, user_id, session_info)
await bus.reply(chunk, context)

# After
source = EventSource.from_string(session_info.source)
await bus.reply(chunk, source)
```

**MessageBus.reply():**
```python
# Before
async def reply(self, content: str, context: TelegramContext) -> None:

# After
async def reply(self, content: str, source: TelegramEventSource) -> None:
    # Access source.chat_id instead of context.chat_id
```

## Files Changed

| File | Change |
|------|--------|
| `core/events.py` | Add EventSource ABC, update Event serialization, remove context helpers, remove old Source class |
| `messagebus/base.py` | Remove MessageContext ABC, update reply signature type hint |
| `messagebus/telegram_bus.py` | Add TelegramEventSource, remove TelegramContext, update reply() |
| `messagebus/discord_bus.py` | Add DiscordEventSource, remove DiscordContext, update reply() |
| `messagebus/cli_bus.py` | Add CliEventSource, remove CliContext, update reply() |
| `server/messagebus_worker.py` | Create typed sources instead of strings |
| `server/delivery_worker.py` | Use source directly, remove `_build_context()` |
| `server/cron_worker.py` | Add CronEventSource, create typed sources |
| `server/agent_worker.py` | Add AgentEventSource (for dispatch results) |
| `tools/subagent_tool.py` | Use AgentEventSource for dispatch events |
| `core/history.py` | Update if needed for source storage |
| Tests | Update all tests for new source types |

## Migration Order

1. Add EventSource ABC to `core/events.py`
2. Add subclass to one file (e.g., `TelegramEventSource`)
3. Update `TelegramBus` to use new source type
4. Update `MessageBusWorker` to create typed source
5. Update `DeliveryWorker` to use source directly
6. Remove `TelegramContext`
7. Repeat for other platforms (Discord, CLI)
8. Add `AgentEventSource` and `CronEventSource`
9. Update remaining workers and tools
10. Remove `MessageContext` ABC and context helpers
11. Update all tests
