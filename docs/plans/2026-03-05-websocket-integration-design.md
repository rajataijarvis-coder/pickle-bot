# WebSocket Integration Design

**Date:** 2026-03-05
**Status:** Approved

## Overview

Add bidirectional WebSocket support to pickle-bot's FastAPI app for real-time event monitoring and chat, with all logic centralized in WebSocketWorker.

## Goals

- Allow WebSocket clients to monitor all EventBus events in real-time
- Allow WebSocket clients to send messages that create InboundEvents
- Integrate cleanly with existing event-driven architecture
- Maintain separation of concerns (worker logic vs HTTP layer)

## Architecture

### High-Level Flow

```
┌─────────────┐
│ WebSocket   │ 1. Connect to ws://host/ws
│   Client    │─────────────────────────────────┐
└─────────────┘                                 │
      │ ▲                                       ▼
      │ │                            ┌──────────────────┐
      │ │ 5. Receive events          │  FastAPI /ws     │
      │ │    (full Event JSON)       │  (thin handoff)  │
      │ │                            └──────────────────┘
      │ │                                     │
      │ │ 2. Send messages                    │ 3. Handoff to worker
      │ │    {source, content,               ▼
      │ │     agent_id?}          ┌──────────────────────────┐
      └───────────────────────────▶   WebSocketWorker        │
                                  │  (in SharedContext)      │
                                  │                          │
                                  │  - Manage connections    │
                                  │  - Handle incoming msgs  │
                                  │  - Normalize to events   │
                                  │  - Broadcast outgoing    │
                                  └──────────────────────────┘
                                           │ ▲
                                           │ │ 4. Subscribe & emit
                                           ▼ │
                                  ┌──────────────────┐
                                  │   EventBus       │
                                  │  (all events)    │
                                  └──────────────────┘
```

### Component Responsibilities

**WebSocketWorker (in SharedContext):**
- Owns `clients: set[WebSocket]` - active connections
- Subscribes to all EventBus events (InboundEvent, OutboundEvent, DispatchEvent, DispatchResultEvent)
- Broadcasts all events to connected clients
- Handles incoming WebSocket messages
- Validates and normalizes to InboundEvent
- Emits InboundEvent to EventBus

**FastAPI `/ws` endpoint:**
- Minimal logic - just accept connection and handoff to worker
- No business logic

**ConnectionManager:**
- Not needed - worker manages connections directly

## Data Formats

### Client → Server (Incoming Messages)

**Schema:**
```json
{
  "source": "user-123",
  "content": "Hello Pickle!",
  "agent_id": "pickle"
}
```

**Validation (Pydantic):**
```python
class WebSocketMessage(BaseModel):
    source: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    agent_id: str | None = None
```

**Rules:**
- `source`: Required, non-empty string (user identifier)
- `content`: Required, non-empty string (message content)
- `agent_id`: Optional string (defaults via routing if null)

**Normalization to InboundEvent:**
```python
# Input
{"source": "user-123", "content": "Hello!", "agent_id": null}

# Output
InboundEvent(
    session_id = "session-abc",  # lookup/create
    agent_id = "pickle",         # from routing
    source = WebSocketEventSource(user_id="user-123"),
    content = "Hello!",
    timestamp = 1709673645.123,  # auto
    retry_count = 0
)
```

### Server → Client (Outgoing Events)

**All event types broadcast as JSON:**
```json
{
  "type": "InboundEvent",
  "session_id": "session-abc",
  "agent_id": "pickle",
  "source": "platform-ws:user-123",
  "content": "Hello!",
  "timestamp": 1709673645.123,
  "retry_count": 0
}
```

```json
{
  "type": "OutboundEvent",
  "session_id": "session-abc",
  "agent_id": "pickle",
  "source": "agent:pickle",
  "content": "Hi there!",
  "timestamp": 1709673646.456,
  "error": null
}
```

**Event type field:** Added during serialization to help clients distinguish event types.

## WebSocketEventSource

### Definition

New EventSource class for WebSocket platform:

```python
@dataclass
class WebSocketEventSource(EventSource):
    """Event from WebSocket client."""
    _namespace = "platform-ws"
    user_id: str

    @classmethod
    def from_string(cls, s: str) -> "WebSocketEventSource":
        """Parse 'platform-ws:user-123'."""
        parts = s.split(":", 1)
        if len(parts) != 2 or parts[0] != cls._namespace:
            raise ValueError(f"Invalid WebSocketEventSource: {s}")
        return cls(user_id=parts[1])

    def __str__(self) -> str:
        return f"{self._namespace}:{self.user_id}"

    @property
    def is_platform(self) -> bool:
        return True
```

### Source Format

- `"platform-ws:user-123"` - User with ID "user-123"
- `"platform-ws:dashboard"` - Dashboard client
- `"platform-ws:mobile-app"` - Mobile app client

**Routing support:**
```yaml
# Can target specific WebSocket sources
routes:
  - pattern: "platform-ws:dashboard"
    agent: "pickle-dashboard"
```

## Error Handling

### Message Validation Errors

**Pydantic ValidationError:**
```python
try:
    msg = WebSocketMessage(**data)
except ValidationError as e:
    await ws.send_json({
        "type": "error",
        "message": f"Validation error: {e}"
    })
    # Don't disconnect - let client retry
```

**Example errors:**
```json
// Missing field
{"type": "error", "message": "Validation error: field required (source)"}

// Empty string
{"type": "error", "message": "Validation error: String should have at least 1 character"}
```

### Connection Errors

**Client disconnect:**
```python
try:
    data = await ws.receive_json()
except WebSocketDisconnect:
    logger.info("Client disconnected")
    self.clients.discard(ws)
except Exception as e:
    logger.error(f"Connection error: {e}")
    self.clients.discard(ws)
```

**Send fails during broadcast:**
```python
for client in self.clients:
    try:
        await client.send_json(event_dict)
    except Exception as e:
        logger.error(f"Failed to send to client: {e}")
        self.clients.discard(client)
```

### Edge Cases

- **No clients connected**: Skip broadcast (no-op)
- **API disabled in config**: Worker still created but may skip EventBus subscription
- **Rapid connect/disconnect**: Set operations are O(1), no issues
- **Very slow client**: Acceptable for "basic resilience" - can upgrade to queues later

## Implementation Details

### WebSocketWorker Methods

```python
class WebSocketWorker(SubscriberWorker):
    def __init__(self, context: SharedContext):
        super().__init__(context)
        self.clients: set[WebSocket] = set()

        # Subscribe to all event types
        for event_class in [InboundEvent, OutboundEvent, DispatchEvent, DispatchResultEvent]:
            self.context.eventbus.subscribe(event_class, self.handle_event)

    async def handle_connection(self, ws: WebSocket):
        """Entry point for FastAPI - manage single connection lifecycle."""
        self.clients.add(ws)
        try:
            await self._run_client_loop(ws)
        finally:
            self.clients.discard(ws)

    async def _run_client_loop(self, ws: WebSocket):
        """Receive and process messages from client."""
        while True:
            try:
                data = await ws.receive_json()
                msg = WebSocketMessage(**data)
                event = self._normalize_message(msg)
                await self.context.eventbus.emit(event)
            except WebSocketDisconnect:
                break
            except ValidationError as e:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

    def _normalize_message(self, msg: WebSocketMessage) -> InboundEvent:
        """Convert WebSocketMessage to InboundEvent."""
        # Determine agent_id (use routing if null)
        agent_id = msg.agent_id
        if agent_id is None:
            agent_id = self._route_message(msg.source, msg.content)

        # Lookup or create session
        session_id = self._get_or_create_session(agent_id, msg.source)

        return InboundEvent(
            session_id=session_id,
            agent_id=agent_id,
            source=WebSocketEventSource(user_id=msg.source),
            content=msg.content,
            timestamp=time.time()
        )

    async def handle_event(self, event: Event):
        """Broadcast event to all connected clients."""
        if not self.clients:
            return

        event_dict = {
            "type": event.__class__.__name__,
            **dataclasses.asdict(event)
        }

        for client in list(self.clients):
            try:
                await client.send_json(event_dict)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                self.clients.discard(client)
```

### FastAPI Endpoint

```python
# In src/picklebot/api/routers/ (or app.py)
from fastapi import WebSocket, Depends
from picklebot.api.deps import get_context
from picklebot.core.context import SharedContext

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ctx: SharedContext = Depends(get_context)
):
    """WebSocket endpoint for real-time event streaming and chat."""
    await websocket.accept()
    await ctx.websocket_worker.handle_connection(websocket)
```

### SharedContext Integration

```python
# In src/picklebot/core/context.py
class SharedContext:
    def __init__(self, ...):
        # ... existing fields ...
        self.websocket_worker: WebSocketWorker | None = None
```

### Server Integration

```python
# In src/picklebot/server/server.py
def _setup_workers(self):
    # ... existing workers ...

    # Create WebSocketWorker and attach to context
    ws_worker = WebSocketWorker(self.context)
    self.context.websocket_worker = ws_worker
    self.workers.append(ws_worker)
```

## Files to Create/Modify

1. **`src/picklebot/api/schemas.py`** - Add `WebSocketMessage` schema
2. **`src/picklebot/server/websocket_worker.py`** - Enhance with full functionality
3. **`src/picklebot/core/events.py`** - Add `WebSocketEventSource` class
4. **`src/picklebot/core/context.py`** - Add `websocket_worker` field
5. **`src/picklebot/server/server.py`** - Create worker and attach to context
6. **`src/picklebot/api/routers/`** - Add `/ws` endpoint
7. **`tests/api/test_schemas.py`** - Test WebSocketMessage validation
8. **`tests/core/test_events.py`** - Test WebSocketEventSource
9. **`tests/server/test_websocket_worker.py`** - Test worker functionality

## Testing Strategy

### Unit Tests

**WebSocketMessage validation:**
- Valid message with all fields
- Valid message with optional agent_id null
- Invalid: missing required fields
- Invalid: empty strings

**WebSocketEventSource:**
- String serialization: `"platform-ws:user-123"`
- Parsing from string
- Invalid format handling

**WebSocketWorker normalization:**
- Message with explicit agent_id
- Message without agent_id (routing)
- Session lookup/creation

### Integration Tests

**Connection lifecycle:**
- Client connects → added to set
- Client sends message → InboundEvent emitted
- Event emitted → broadcast to client
- Client disconnects → removed from set

**Error handling:**
- Invalid message → error sent back, connection stays
- Send failure → client removed
- No clients → broadcast no-op

### Manual Testing

```bash
# Connect
wscat -c ws://localhost:8000/ws

# Send message
> {"source": "test-user", "content": "Hello Pickle", "agent_id": "pickle"}

# Receive events
< {"type": "InboundEvent", ...}
< {"type": "OutboundEvent", ...}

# Test validation error
> {"source": ""}
< {"type": "error", "message": "Validation error: ..."}
```

## Success Criteria

- [ ] WebSocket clients can connect and receive all EventBus events in real-time
- [ ] WebSocket clients can send messages that create InboundEvents
- [ ] Invalid messages return validation errors (no disconnect)
- [ ] Connection errors handled gracefully (log + remove client)
- [ ] WebSocketEventSource integrates with routing system
- [ ] All unit and integration tests passing
- [ ] Manual testing confirms bidirectional communication works

## Future Enhancements (Not In Scope)

- Session/agent subscription filtering (broadcast all for now)
- Authentication/authorization (no auth for now)
- Event buffering for reconnection (basic resilience for now)
- Per-client queues for slow client isolation (simple broadcast for now)
