# Default Routing Design

Add fallback to `default_agent` when no routing bindings match.

## Overview

**Current behavior:** Messages without matching routing bindings are skipped.

**New behavior:** Messages without matching routing bindings are routed to `config.default_agent`.

## Requirements

- Use existing `default_agent` field from config (already required)
- Silent operation (no special logging when default is used)
- Always active (no configuration flag needed)
- Fallback logic in `RoutingTable.resolve()`

## Component Changes

### 1. RoutingTable (`src/picklebot/core/routing.py`)

Change `resolve()` to return `default_agent` when no bindings match:

```python
def resolve(self, source: str) -> str:
    """Return agent_id for source, falling back to default_agent if no match."""
    for binding in self._load_bindings():
        if binding.pattern.match(source):
            return binding.agent
    return self._context.config.default_agent
```

**Changes:**
- Return type: `str | None` → `str`
- Always returns a valid agent ID

### 2. MessageBusWorker (`src/picklebot/server/messagebus_worker.py`)

Remove the `None` check since routing always succeeds:

```python
# Remove lines 82-84:
# if not agent_id:
#     self.logger.debug(f"No routing match for {source}")
#     return
```

### 3. Tests (`tests/core/test_routing.py`)

Update `test_routing_table_resolve_no_match`:

```python
def test_routing_table_resolve_fallback_to_default():
    """RoutingTable should return default_agent if no pattern matches."""
    context = MockContext(
        [
            {"agent": "pickle", "value": "telegram:.*"},
        ]
    )
    context.config.default_agent = "pickle"
    table = RoutingTable(context)

    assert table.resolve("discord:123") == "pickle"
```

Update `MockConfig` to include `default_agent`:

```python
class MockConfig:
    def __init__(self, bindings, default_agent="pickle"):
        self.routing = {"bindings": bindings}
        self.default_agent = default_agent
```

## Flow

```
Incoming message (source: "discord:999")
        │
        ▼
RoutingTable.resolve("discord:999")
        │
        ├─ Check bindings → no match
        │
        ▼
Return config.default_agent
        │
        ▼
Message routed to default agent
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No bindings configured | Routes to `default_agent` |
| Empty bindings list | Routes to `default_agent` |
| All bindings are platform-specific | Unknown platform routes to `default_agent` |

## Files Changed

| File | Change |
|------|--------|
| `src/picklebot/core/routing.py` | `resolve()` returns default_agent instead of None |
| `src/picklebot/server/messagebus_worker.py` | Remove None check |
| `tests/core/test_routing.py` | Update tests for new behavior |
