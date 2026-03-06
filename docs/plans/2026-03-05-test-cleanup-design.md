# Test Cleanup Design

## Problem

The test suite has 549 tests, many of which are trivial "property access" tests that verify Python's dataclass behavior rather than actual business logic. Examples:

- Tests that create an object and check `obj.field == expected`
- Tests that verify a method exists on a class
- Redundant serialization tests that could be covered by roundtrip tests

## Goals

1. **Reduce test count** - Remove trivial tests that don't add value
2. **Improve test quality** - Consolidate simple tests into meaningful roundtrip tests

## Approach

**Delete liberally + Roundtrip tests** - Tests that verify `event.session_id == "sess-1"` after construction are testing Python, not our code. Keep only tests that verify actual logic or integration points.

## Phase 1: Events Module (Template)

Start with `tests/events/` as the template for other modules.

### File-by-File Plan

| File | Before | After | Action |
|------|--------|-------|--------|
| `test_types.py` | 475 lines, 26 tests | ~80 lines, 5 tests | Rewrite |
| `test_source.py` | 152 lines, 12 tests | ~40 lines, 3 tests | Rewrite |
| `test_bus.py` | 124 lines, 5 tests | Same | Keep |
| `test_bus_persistence.py` | 182 lines, 7 tests | Same | Keep |
| `test_bus_recovery.py` | 90 lines, 3 tests | Same | Keep |
| `test_retry.py` | 30 lines, 5 tests | Same | Keep |
| `test_websocket_stub.py` | 57 lines, 3 tests | Delete | Remove |

**Total: 64 tests → 28 tests** (56% reduction)

### New Test Structures

**test_types.py (26 → 5 tests):**

```python
@pytest.mark.parametrize("event_type", ["inbound", "outbound", "dispatch", "dispatch_result"])
def test_event_roundtrip(event_type):
    """Roundtrip test covers creation, serialization, deserialization."""
    # Creates event, serializes, deserializes, verifies all fields match

def test_event_with_error_roundtrip():
    """Tests OutboundEvent and DispatchResultEvent error field."""

def test_unknown_type_raises():
    """Already exists - keep."""
```

**test_source.py (12 → 3 tests):**

```python
@pytest.mark.parametrize("source_cls,args,expected_str", [
    (AgentEventSource, {"agent_id": "pickle"}, "agent:pickle"),
    (CronEventSource, {"cron_id": "daily"}, "cron:daily"),
    (TelegramEventSource, {"user_id": "123", "chat_id": "456"}, "platform-telegram:123:456"),
    (DiscordEventSource, {"user_id": "123", "channel_id": "456"}, "platform-discord:123:456"),
    (CliEventSource, {}, "platform-cli:default"),
])
def test_source_roundtrip(source_cls, args, expected_str):
    source = source_cls(**args)
    assert str(source) == expected_str
    restored = source_cls.from_string(expected_str)
    assert restored == source

def test_abstract_base_cannot_instantiate():
    """Keep - tests ABC enforcement."""

def test_unknown_namespace_raises():
    """Keep - tests error handling."""
```

## Cleanup Patterns (Apply to Other Modules)

1. **Replace creation/property tests** with roundtrip tests
2. **Use `@pytest.mark.parametrize`** for similar tests across types
3. **Keep tests that verify actual logic** (not Python behavior)
4. **Delete stub tests** that only check method existence

## Modules to Apply Pattern (Future Phases)

After events module is complete, apply same patterns to:

- `tests/provider/` - Base class tests are trivial
- `tests/api/` - Many endpoint tests could be consolidated
- `tests/server/` - Worker tests have redundancy
- `tests/utils/` - Definition loader tests are verbose

## Success Criteria

- All tests pass after cleanup
- Test count reduced by ~50% in cleaned modules
- No loss of coverage for actual business logic
- Pattern documented for future test writing
