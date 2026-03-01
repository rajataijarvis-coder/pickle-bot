# Message Routing Design

Unified inbound and outbound message routing with simplified configuration.

## Overview

**Inbound:** Route incoming messages to the correct agent based on configurable regex bindings. Priority is inferred from pattern specificity.

**Outbound:** Deliver responses to the originating platform by looking up session source. No proactive fallback.

## Config Structure

### User Config (`config.user.yaml`)

Platform credentials and allow lists only:

```yaml
messagebus:
  enabled: true

  telegram:
    enabled: true
    bot_token: "..."
    allowed_user_ids: ["123", "456"]

  discord:
    enabled: true
    bot_token: "..."
    allowed_user_ids: []
```

### Runtime Config (`config.runtime.yaml`)

Routing rules and source cache:

```yaml
routing:
  bindings:
    - agent: cookie
      value: "telegram:123456"
    - agent: pickle
      value: "telegram:.*"
    - agent: pickle
      value: ".*"

sources:
  "telegram:123456":
    session_id: "uuid-abc"
  "discord:789":
    session_id: "uuid-xyz"
```

### Removed Fields

From user config:
- `messagebus.default_platform`
- `messagebus.telegram.default_chat_id`
- `messagebus.discord.default_chat_id`
- `messagebus.telegram.sessions`
- `messagebus.discord.sessions`

## Architecture

```
Inbound Flow:
─────────────────────────────────────────────────────────────
Platform Message → MessageBusWorker
                        │
                        ▼
                  Build source: "telegram:123456"
                        │
                        ▼
                  RoutingTable.resolve(source)
                        │
                        ▼
                  agent_id (or skip if no match)
                        │
                        ▼
                  Check sources cache for session_id
                        │
                        ├─ Hit → Use cached session_id
                        └─ Miss → Create session, cache it
                        │
                        ▼
                  Publish InboundEvent

Outbound Flow:
─────────────────────────────────────────────────────────────
OutboundEvent → DeliveryWorker
                        │
                        ▼
                  _get_session_source(session_id) [LRU cached]
                        │
                        ├─ Found → Parse source, get platform
                        └─ Not found → Skip delivery
                        │
                        ▼
                  Deliver to platform
```

## Components

### core/routing.py (New)

```python
@dataclass
class Binding:
    agent: str
    value: str
    tier: int = field(init=False)
    pattern: Pattern = field(init=False)

    def __post_init__(self):
        self.pattern = re.compile(f"^{self.value}$")
        self.tier = self._compute_tier()

    def _compute_tier(self) -> int:
        """
        0 = exact literal (no regex chars)
        1 = specific regex (anchors, character classes)
        2 = wildcard (. or .*)
        """
        if not any(c in self.value for c in r".*+?[]()|^$"):
            return 0
        if ".*" in self.value:
            return 2
        return 1


class RoutingTable:
    def __init__(self, context: "SharedContext"):
        self._context = context
        self._bindings: list[Binding] | None = None
        self._config_hash: int | None = None

    def _load_bindings(self) -> list[Binding]:
        """Load and sort bindings from config. Cached until config changes."""
        current_hash = hash(tuple(
            (b["agent"], b["value"])
            for b in self._context.config.routing.get("bindings", [])
        ))

        if self._bindings is not None and self._config_hash == current_hash:
            return self._bindings

        bindings = [
            Binding(agent=b["agent"], value=b["value"])
            for b in self._context.config.routing.get("bindings", [])
        ]
        bindings.sort(key=lambda b: (b.tier, id(b)))  # tier, then order

        self._bindings = bindings
        self._config_hash = current_hash
        return bindings

    def resolve(self, source: str) -> str | None:
        """Return agent_id for source, or None if no match."""
        for binding in self._load_bindings():
            if binding.pattern.match(source):
                return binding.agent
        return None
```

### server/messagebus_worker.py (Modified)

**Changes:**
- Remove pre-loaded default agent
- Use RoutingTable to resolve agent from source
- Use sources cache for session lookup
- Only update cache when session_id changes

```python
class MessageBusWorker(Worker):
    def __init__(self, context: "SharedContext"):
        super().__init__(context)
        self.buses = context.messagebus_buses
        self.bus_map = {bus.platform_name: bus for bus in self.buses}

    def _get_or_create_session_id(self, source: str, agent_id: str) -> str:
        """Get existing session_id from source cache, or create new session."""
        source_info = self._context.config.sources.get(source)
        if source_info:
            return source_info["session_id"]

        agent_def = self._context.agent_loader.load(agent_id)
        agent = Agent(agent_def, self._context)
        session = agent.new_session(source)

        self._context.config.set_runtime(
            f"sources.{source}",
            {"session_id": session.session_id}
        )
        return session.session_id

    async def _create_callback(self, platform: str):
        async def callback(message: str, context: Any) -> None:
            bus = self.bus_map[platform]
            if not bus.is_allowed(context):
                return

            user_id = context.user_id
            source = f"{platform}:{user_id}"
            agent_id = self._context.routing_table.resolve(source)

            if not agent_id:
                self.logger.debug(f"No routing match for {source}")
                return

            session_id = self._get_or_create_session_id(source, agent_id)

            event = InboundEvent(
                session_id=session_id,
                agent_id=agent_id,
                source=source,
                content=message,
                timestamp=time.time(),
                context=context,
            )
            await self._context.eventbus.publish(event)

        return callback
```

### server/delivery_worker.py (Modified)

**Changes:**
- Remove `_lookup_platform()` that scans config
- Remove proactive source fallback
- Add LRU cache for session lookup
- Skip delivery if no source found

```python
from functools import lru_cache

class DeliveryWorker(SubscriberWorker):
    def __init__(self, context: "SharedContext"):
        super().__init__(context)
        self.context.eventbus.subscribe(EventType.OUTBOUND, self.handle_event)

    @lru_cache(maxsize=10)
    def _get_session_source(self, session_id: str) -> HistorySession | None:
        """Get session info from HistoryStore (cached)."""
        for session in self.context.history_store.list_sessions():
            if session.id == session_id:
                return session
        return None

    async def handle_event(self, event: OutboundEvent) -> None:
        try:
            session_info = self._get_session_source(event.session_id)

            if not session_info or not session_info.source:
                self.logger.warning(f"No source for session {event.session_id}, skipping")
                return

            platform, user_id = session_info.source.split(":", 1)
            context = self._build_context(platform, user_id, session_info)

            limit = PLATFORM_LIMITS.get(platform, float("inf"))
            chunks = chunk_message(event.content, int(limit) if limit != float("inf") else len(event.content))

            bus = self._get_bus(platform)
            for chunk in chunks:
                await bus.reply(chunk, context)

            self.context.eventbus.ack(event)

        except Exception as e:
            self.logger.error(f"Failed to deliver: {e}")

    def _build_context(self, platform: str, user_id: str, session_info: HistorySession) -> MessageContext:
        if platform == "telegram":
            return TelegramContext(user_id=user_id, chat_id=user_id)
        elif platform == "discord":
            stored = session_info.context or {}
            return DiscordContext(user_id=user_id, channel_id=stored.get("channel_id", user_id))
        else:
            raise ValueError(f"Unknown platform: {platform}")
```

### utils/config.py (Modified)

**Add fields:**

```python
class Config(BaseModel):
    # ... existing fields ...

    # New runtime fields
    routing: dict = Field(default_factory=lambda: {"bindings": []})
    sources: dict[str, dict] = Field(default_factory=dict)
```

**Remove from platform configs:**
- `TelegramConfig.sessions`
- `TelegramConfig.default_chat_id`
- `DiscordConfig.sessions`
- `DiscordConfig.default_chat_id`
- `MessageBusConfig.default_platform`

### core/context.py (Modified)

**Add:**

```python
class SharedContext:
    def __init__(self, config: Config, ...):
        # ... existing initialization ...
        self.routing_table = RoutingTable(self)
```

## Routing Rules

### Tier Computation

| Tier | Pattern Type | Example |
|------|-------------|---------|
| 0 | Exact literal | `telegram:123456` |
| 1 | Specific regex | `telegram:[0-9]+` |
| 2 | Wildcard | `telegram:.*`, `.*` |

### Matching Logic

1. Sort bindings by tier (ascending), then by config order
2. First pattern that matches wins
3. If no match, skip message (don't process)

### Example

```yaml
bindings:
  - agent: cookie
    value: "telegram:123456"    # tier 0 - exact match
  - agent: pickle
    value: "telegram:.*"         # tier 2 - any telegram
  - agent: pickle
    value: ".*"                  # tier 2 - catch all
```

For source `telegram:123456`:
- Matches `telegram:123456` (tier 0) → agent: cookie

For source `telegram:789`:
- Doesn't match `telegram:123456`
- Matches `telegram:.*` (tier 2, first in order) → agent: pickle

## Migration Notes

1. Remove `sessions` and `default_chat_id` from user config
2. Create initial `routing.bindings` in runtime config
3. Source cache populates automatically as messages arrive
4. DeliveryWorker no longer needs platform session mappings

## Files Changed

| File | Change |
|------|--------|
| `core/routing.py` | New file |
| `core/context.py` | Add RoutingTable initialization |
| `server/messagebus_worker.py` | Use RoutingTable, source cache |
| `server/delivery_worker.py` | Simplify, add LRU cache |
| `utils/config.py` | Add routing/sources fields, remove old platform fields |
