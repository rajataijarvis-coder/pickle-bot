# CLI Agent Selection Design

**Date:** 2026-03-04
**Status:** Approved

## Problem Statement

The CLI chat command currently:
1. Hardcodes `agent_id="default"` - no way to select different agents
2. Hardcodes `session_id="cli-session"` - same session reused across invocations
3. Doesn't validate agent existence until first message is sent

## Solution Overview

Add `--agent` flag to chat command for agent selection, validate agent at startup, and generate unique session IDs.

## Design

### 1. CLI Flag Addition

**File:** `src/picklebot/cli/chat.py`

Add `--agent` / `-a` optional flag to `chat_command`:

```python
def chat_command(
    ctx: typer.Context,
    agent: str = typer.Option(
        None,
        "--agent", "-a",
        help="Agent ID to use for chat (default: from config.default_agent)"
    )
) -> None:
    """Start interactive chat session."""
    config = ctx.obj.get("config")
    agent_id = agent or config.default_agent

    setup_logging(config, console_output=False)

    chat_loop = ChatLoop(config, agent_id)
    asyncio.run(chat_loop.run())
```

### 2. ChatLoop Agent Validation

**File:** `src/picklebot/cli/chat.py`

Modify `ChatLoop.__init__` to:
- Accept `agent_id` parameter
- Validate agent exists at startup
- Fail fast with user-friendly error if agent not found
- Generate unique session ID

```python
class ChatLoop:
    """Interactive chat session using event-driven architecture."""

    def __init__(self, config: Config, agent_id: str):
        self.config = config
        self.agent_id = agent_id
        self.console = Console()

        # Validate agent exists at startup
        from picklebot.utils.def_loader import DefNotFoundError
        try:
            self.context.agent_loader.load(agent_id)
        except DefNotFoundError as e:
            self.console.print(f"[red]Error: Agent '{agent_id}' not found[/red]")
            self.console.print(f"\nAvailable agents:")
            for agent_def in self.context.agent_loader.discover_agents():
                self.console.print(f"  - {agent_def.id}")
            raise SystemExit(1)

        # Generate unique session ID for this chat invocation
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_id = f"cli-{timestamp}"

        self.context = SharedContext(config=config, buses=[])
        # ... rest of init
```

### 3. Use Validated agent_id in Events

**File:** `src/picklebot/cli/chat.py`

Update `ChatLoop.run()` to use validated `self.agent_id` and `self.session_id`:

```python
event = InboundEvent(
    session_id=self.session_id,
    agent_id=self.agent_id,  # Use validated agent_id
    source=CliEventSource(),
    content=user_input,
)
```

### 4. Error Handling

**Startup errors (fail fast):**
- Agent not found → Display error, list available agents, exit
- Agent definition invalid → Display error, exit

**Runtime errors (existing behavior):**
- Handled by AgentWorker → Error in OutboundEvent → Displayed to user

## Session ID Format

**Before:** `"cli-session"` (static, reused)

**After:** `"cli-{timestamp}"` (unique per invocation)

Examples:
- `cli-20260304-143025`
- `cli-20260304-150312`

Benefits:
- Fresh history per chat invocation
- Easier debugging in logs
- No cross-session contamination

## User Experience

### Normal Usage

```bash
# Use default agent from config
uv run picklebot chat

# Use specific agent
uv run picklebot chat --agent cookie
uv run picklebot chat -a cookie
```

### Error Case: Agent Not Found

```bash
$ uv run picklebot chat --agent nonexistent
Error: Agent 'nonexistent' not found

Available agents:
  - default
  - cookie
  - assistant
```

### Success Case: Agent Found

```bash
$ uv run picklebot chat --agent cookie
╭─────────────────╮
│ Welcome to pickle-bot! │
╰─────────────────╯
Type 'quit' or 'exit' to end the session.

You: Hello!
Agent: Hello! I'm Cookie, your helpful assistant.
```

## Implementation Notes

### Order of Operations

1. Parse CLI flag
2. Resolve agent_id (flag or config.default_agent)
3. Create ChatLoop with agent_id
4. Validate agent exists (fail fast if not)
5. Generate unique session_id
6. Start event loop
7. Use validated agent_id in all InboundEvents

### No Architecture Changes

- Keep EventBus + AgentWorker (event-driven)
- Keep OutboundEvent subscription
- Keep response queue mechanism
- Only add validation layer at startup

### Backward Compatibility

- No `--agent` flag → uses `config.default_agent` (same as before)
- Existing behavior preserved
- Only adds new optional functionality

## Testing Considerations

1. **Test valid agent selection:**
   - `chat --agent cookie` starts successfully
   - Messages use correct agent

2. **Test invalid agent error:**
   - `chat --agent nonexistent` fails fast
   - Error message shows available agents

3. **Test default agent:**
   - `chat` uses config.default_agent
   - Works as before

4. **Test session uniqueness:**
   - Multiple chat invocations get different session IDs
   - No history contamination

## Files Modified

1. `src/picklebot/cli/chat.py`:
   - Add `--agent` flag to chat_command
   - Modify ChatLoop.__init__ for validation
   - Update ChatLoop.run to use self.agent_id

2. `tests/cli/test_chat_integration.py`:
   - Add test for agent selection
   - Add test for invalid agent error

## Success Criteria

- [ ] `--agent` flag works
- [ ] Invalid agent fails fast with helpful error
- [ ] Default agent behavior preserved
- [ ] Unique session IDs per invocation
- [ ] All existing tests pass
- [ ] New tests for agent selection
