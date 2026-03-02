# Default Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Route messages to `default_agent` when no routing bindings match.

**Architecture:** Update `RoutingTable.resolve()` to return `default_agent` instead of `None`. Remove the `None` check from `MessageBusWorker`. Update tests to verify fallback behavior.

**Tech Stack:** Python 3.13, pytest, pydantic

---

### Task 1: Update MockConfig for tests

**Files:**
- Modify: `tests/core/test_routing.py:53-56`

**Step 1: Update MockConfig to include default_agent**

```python
class MockConfig:
    def __init__(self, bindings, default_agent="pickle"):
        self.routing = {"bindings": bindings}
        self.default_agent = default_agent
```

**Step 2: Run tests to verify they still pass**

Run: `uv run pytest tests/core/test_routing.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/core/test_routing.py
git commit -m "test: add default_agent to MockConfig"
```

---

### Task 2: Update RoutingTable.resolve() return type

**Files:**
- Modify: `src/picklebot/core/routing.py:69-74`

**Step 1: Write failing test for fallback behavior**

Add to `tests/core/test_routing.py`:

```python
def test_routing_table_resolve_fallback_to_default():
    """RoutingTable should return default_agent if no pattern matches."""
    context = MockContext(
        [
            {"agent": "pickle", "value": "telegram:.*"},
        ],
        default_agent="cookie",
    )
    table = RoutingTable(context)

    assert table.resolve("discord:123") == "cookie"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_routing.py::test_routing_table_resolve_fallback_to_default -v`
Expected: FAIL with AssertionError (returns None instead of "cookie")

**Step 3: Update RoutingTable.resolve() implementation**

Modify `src/picklebot/core/routing.py`:

```python
def resolve(self, source: str) -> str:
    """Return agent_id for source, falling back to default_agent if no match."""
    for binding in self._load_bindings():
        if binding.pattern.match(source):
            return binding.agent
    return self._context.config.default_agent
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_routing.py::test_routing_table_resolve_fallback_to_default -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/core/routing.py tests/core/test_routing.py
git commit -m "feat(routing): fallback to default_agent when no bindings match"
```

---

### Task 3: Update existing no-match test

**Files:**
- Modify: `tests/core/test_routing.py:89-99`

**Step 1: Update test_routing_table_resolve_no_match**

Rename and update the test:

```python
def test_routing_table_resolve_no_match_returns_default():
    """RoutingTable should return default_agent if no pattern matches."""
    context = MockContext(
        [
            {"agent": "pickle", "value": "telegram:.*"},
        ],
        default_agent="cookie",
    )
    table = RoutingTable(context)

    assert table.resolve("discord:123") == "cookie"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/core/test_routing.py::test_routing_table_resolve_no_match_returns_default -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/core/test_routing.py
git commit -m "refactor(test): update no-match test to verify default fallback"
```

---

### Task 4: Remove None check from MessageBusWorker

**Files:**
- Modify: `src/picklebot/server/messagebus_worker.py:79-84`

**Step 1: Write test verifying all messages are routed**

Add to `tests/server/test_messagebus_worker.py`:

```python
def test_messagebus_worker_routes_unknown_source_to_default(mock_context):
    """MessageBusWorker should route unknown sources to default_agent."""
    mock_context.config.routing = {"bindings": []}
    mock_context.config.default_agent = "pickle"
    mock_context.routing_table = RoutingTable(mock_context)

    worker = MessageBusWorker(mock_context)
    callback = worker._create_callback("telegram")

    # This should NOT be skipped even with empty bindings
    asyncio.run(callback("hello", TelegramContext(user_id="999", chat_id="999")))

    # Verify event was published
    assert mock_context.eventbus.publish.called
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/server/test_messagebus_worker.py::test_messagebus_worker_routes_unknown_source_to_default -v`
Expected: FAIL (message is skipped due to None check)

**Step 3: Remove the None check from MessageBusWorker**

Modify `src/picklebot/server/messagebus_worker.py`, remove lines 82-84:

```python
# Before:
agent_id = self.context.routing_table.resolve(source)

if not agent_id:
    self.logger.debug(f"No routing match for {source}")
    return

session_id = self._get_or_create_session_id(source, agent_id)

# After:
agent_id = self.context.routing_table.resolve(source)

session_id = self._get_or_create_session_id(source, agent_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/server/test_messagebus_worker.py::test_messagebus_worker_routes_unknown_source_to_default -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/picklebot/server/messagebus_worker.py tests/server/test_messagebus_worker.py
git commit -m "refactor(messagebus): remove None check, routing always succeeds"
```

---

### Task 5: Run all tests and verify

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 2: Run linter**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 3: Final commit if any formatting changes**

```bash
git add -A
git commit -m "style: format code" || echo "No formatting changes needed"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Update MockConfig | `tests/core/test_routing.py` |
| 2 | Add fallback to RoutingTable | `src/picklebot/core/routing.py`, `tests/core/test_routing.py` |
| 3 | Update no-match test | `tests/core/test_routing.py` |
| 4 | Remove None check | `src/picklebot/server/messagebus_worker.py`, `tests/server/test_messagebus_worker.py` |
| 5 | Verify all tests pass | - |

## Testing Strategy

1. Unit tests for `RoutingTable.resolve()` fallback behavior
2. Integration test for `MessageBusWorker` routing unknown sources
3. Full test suite verification

## Dependencies

None - uses existing `default_agent` field from config.
