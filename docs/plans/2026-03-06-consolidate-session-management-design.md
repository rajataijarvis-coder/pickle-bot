# Consolidate Session Management into RoutingTable

**Date:** 2026-03-06
**Status:** Design Approved

## Overview

Consolidate duplicated session management logic into RoutingTable to improve code reuse, reduce config coupling, and establish single responsibility for source-to-session mapping.

## Problem

- `_get_or_create_session_id` is duplicated in both `ChannelWorker` and `WebSocketWorker`
- `config.set_runtime` calls are scattered across multiple workers
- Session management logic is not co-located with related routing logic

## Solution

Add a single method to RoutingTable that handles session cache lookup and creation, while keeping session storage in config.

## Design

### Architecture

**New RoutingTable method:**

```python
def get_or_create_session_id(self, source: EventSource, agent_id: str) -> str:
    """Get existing session_id from source cache, or create new session.

    Args:
        source: Typed EventSource object (e.g., TelegramEventSource, WebSocketEventSource)
        agent_id: Agent identifier to use for session creation

    Returns:
        session_id: Existing or newly created session identifier

    Raises:
        Propagates exceptions from agent loading and session creation
    """
```

### Implementation

The method will:

1. Check `config.sources[str(source)]` for existing session_id
2. If found, return it immediately
3. If not found, create a new session via Agent workflow:
   - Load agent definition via `agent_loader.load(agent_id)`
   - Create Agent instance
   - Call `agent.new_session(source)`
4. Store the new session_id in config via `config.set_runtime()`
5. Return the session_id

**Code:**

```python
def get_or_create_session_id(self, source: EventSource, agent_id: str) -> str:
    source_str = str(source)

    # Check cache first
    source_info = self._context.config.sources.get(source_str)
    if source_info:
        return source_info["session_id"]

    # Create new session
    agent_def = self._context.agent_loader.load(agent_id)
    agent = Agent(agent_def, self._context)
    session = agent.new_session(source)

    # Cache the session
    self._context.config.set_runtime(
        f"sources.{source_str}",
        {"session_id": session.session_id}
    )

    return session.session_id
```

**Required imports in routing.py:**
- `from picklebot.core.agent import Agent`
- `from picklebot.core.events import EventSource`

### Worker Changes

**ChannelWorker (`server/channel_worker.py`):**

- Remove `_get_or_create_session_id` method (~15 lines)
- Update call sites:

```python
# Before:
session_id = self._get_or_create_session_id(source_str, agent_id)

# After:
source = EventSource.from_string(source_str)
session_id = self._context.routing.get_or_create_session_id(source, agent_id)
```

**WebSocketWorker (`server/websocket_worker.py`):**

- Remove `_get_or_create_session_id` method (~15 lines)
- Update call sites:

```python
# Before:
session_id = self._get_or_create_session_id(source, agent_id)

# After:
session_id = self._context.routing.get_or_create_session_id(source, agent_id)
```

### Scope

**In scope:**
- Session cache lookup and creation logic
- Source-to-session mapping
- Reducing code duplication

**Out of scope:**
- `default_delivery_source` handling (remains untouched)
- Changes to config storage mechanism
- Changes to Agent or AgentSession behavior

### Error Handling

Keep existing behavior - let exceptions propagate:
- Agent not found → exception from `agent_loader.load()`
- Invalid source → exception from EventSource validation
- Session creation failure → exception from `agent.new_session()`

Workers continue to handle exceptions as they currently do.

## Testing

### New Tests

Add to `tests/core/test_routing.py`:
- Session cache hit (existing session returns immediately)
- Session cache miss (new session created and cached)
- Config update verification (ensure `set_runtime` called correctly)
- Exception propagation (agent not found, etc.)

### Updated Tests

Update `tests/server/test_channel_worker.py`:
- Mock `routing.get_or_create_session_id` instead of internal method

Update `tests/server/test_websocket_worker.py`:
- Mock `routing.get_or_create_session_id` instead of internal method

## Migration Path

1. Add `get_or_create_session_id` to RoutingTable with full test coverage
2. Update ChannelWorker, remove duplicate method
3. Update WebSocketWorker, remove duplicate method
4. Run full test suite to verify no regressions
5. Commit as single refactoring PR

## Benefits

- **Code reuse:** ~30 lines of duplicated code eliminated
- **Single responsibility:** RoutingTable owns source-related logic
- **Reduced coupling:** Workers don't directly call `config.set_runtime`
- **Maintainability:** One place to update session management logic
- **Testability:** Easier to mock and test session behavior

## Risks

- Minimal risk - no behavior changes, only code movement
- RoutingTable scope expands slightly (acceptable given tight coupling to source routing)
