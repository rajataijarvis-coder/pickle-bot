# Test Suite Cleanup Design

**Date:** 2026-03-01
**Goal:** Remove duplicates, extract common fixtures, and consolidate scattered tests.

## Current State

- **Total:** 9,275 lines across 63 test files
- **Issues:**
  1. Duplicate event tests across 3 files
  2. Duplicate DeliveryWorker tests across 2 files
  3. Duplicate API test fixtures across 3 files
  4. Duplicate MessageBus lifecycle tests across 2 files
  5. SharedContext tests scattered across 3 files
  6. Repeated test agent creation patterns throughout

## Approach: Layered Cleanup

Three logical layers, each addressing a specific concern.

---

## Layer 1: Fixtures & Helpers

**Goal:** Centralize common test setup in `conftest.py` and create reusable factories.

### 1.1 Enhanced `conftest.py` Fixtures

New fixtures to add:

```python
# --- API Test Fixtures ---
@pytest.fixture
def api_client(tmp_path):
    """TestClient with pre-configured workspace. Yields (client, workspace)."""

@pytest.fixture
def api_client_with_agent(api_client):
    """TestClient with a test agent already created."""

@pytest.fixture
def api_client_with_skill(api_client):
    """TestClient with a test skill already created."""

@pytest.fixture
def api_client_with_cron(api_client):
    """TestClient with a test cron already created."""

# --- Mock Context Fixtures ---
@pytest.fixture
def mock_context(tmp_path):
    """Mock SharedContext for worker tests (no real agent loading)."""

# --- Event Fixtures ---
@pytest.fixture
def sample_inbound_event():
    """Factory fixture to create InboundEvent instances."""

@pytest.fixture
def sample_outbound_event():
    """Factory fixture to create OutboundEvent instances."""

@pytest.fixture
def sample_dispatch_event():
    """Factory fixture to create DispatchEvent instances."""
```

### 1.2 Test Definition Factories

New file: `tests/helpers.py`

```python
def create_test_agent(workspace, agent_id="test-agent", **kwargs):
    """Create a minimal test agent in workspace."""

def create_test_skill(workspace, skill_id="test-skill", **kwargs):
    """Create a minimal test skill in workspace."""

def create_test_cron(workspace, cron_id="test-cron", **kwargs):
    """Create a minimal test cron in workspace."""
```

**Files Changed:**
- `tests/conftest.py` - Add ~80 lines
- `tests/helpers.py` - New file, ~50 lines

---

## Layer 2: File Consolidation

**Goal:** Merge duplicate test files and consolidate scattered tests.

### 2.1 Event Tests: 3 files → 2 files

| Current | Lines | Action |
|---------|-------|--------|
| `core/test_events.py` | 263 | Merge into `events/test_event_types.py` |
| `events/test_types.py` | 310 | Merge into `events/test_event_types.py` |
| `events/test_bus.py` | 124 | Keep as `events/test_event_bus.py` |

**Result:**
- `events/test_event_types.py` (~350 lines) - Event class tests
- `events/test_event_bus.py` (~130 lines) - EventBus tests

**Savings:** ~120 lines from deduplication

### 2.2 DeliveryWorker Tests: 2 files → 1 file

| Current | Lines | Action |
|---------|-------|--------|
| `events/test_delivery.py` | 151 | Merge into `server/test_delivery_worker.py` |
| `server/test_delivery_worker.py` | 111 | Keep as primary |

**Result:** `server/test_delivery_worker.py` (~180 lines)
**Savings:** ~80 lines from duplicate mock_context and tests

### 2.3 SharedContext Tests: 3 files → 1 file

| Current | Lines | Action |
|---------|-------|--------|
| `core/test_context.py` | 21 | Keep as primary, expand |
| `core/test_context_eventbus.py` | 83 | Merge into `test_context.py` |
| `core/test_context_buses.py` | 86 | Merge into `test_context.py` |

**Result:** `core/test_context.py` (~150 lines)
**Savings:** ~40 lines from dedup and organization

### 2.4 API Tests: Extract fixtures

Keep `test_agents.py`, `test_skills.py`, `test_crons.py` separate but:
- Remove duplicate `client` fixture from each
- Use centralized `api_client_with_*` fixtures from conftest.py

**Savings:** ~60 lines across 3 files

**Files to Delete:**
- `tests/core/test_events.py`
- `tests/events/test_types.py`
- `tests/core/test_context_eventbus.py`
- `tests/core/test_context_buses.py`
- `tests/events/test_delivery.py`

---

## Layer 3: Test Patterns

**Goal:** Use parametrization to reduce duplicated test logic.

### 3.1 MessageBus Lifecycle Tests

Current: `test_telegram_bus.py` and `test_discord_bus.py` each have 5 identical lifecycle tests.

**After:** Single parametrized test class in `test_base.py`:

```python
@pytest.mark.parametrize("bus_type", ["telegram", "discord"])
class TestMessageBusLifecycle:
    """Shared lifecycle tests for all bus implementations."""

    @pytest.mark.anyio
    async def test_run_stop_lifecycle(self, bus_type): ...

    @pytest.mark.anyio
    async def test_run_raises_on_second_call(self, bus_type): ...

    @pytest.mark.anyio
    async def test_stop_is_idempotent(self, bus_type): ...

    @pytest.mark.anyio
    async def test_stop_without_run_is_safe(self, bus_type): ...

    @pytest.mark.anyio
    async def test_can_rerun_after_stop(self, bus_type): ...
```

**Savings:** ~100 lines

### 3.2 Platform-Specific Tests Stay Separate

- `test_telegram_bus.py` - Telegram-specific reply/post tests
- `test_discord_bus.py` - Discord-specific reply/post tests
- `test_base.py` - Shared lifecycle + whitelist tests

### 3.3 Remove Obsolete/Redundant Tests

| Test | Reason |
|------|--------|
| `test_deserialize_uses_class_name_not_enum_value` (duplicate) | Already tested in both files |
| `test_event_bus_creation` | Trivial assertion, no value |
| Multiple identical roundtrip tests | Consolidate to one per event type |

**Savings:** ~50 lines

---

## Summary

| Layer | Action | Lines Removed | Lines Added |
|-------|--------|---------------|-------------|
| 1 | New fixtures/helpers | 0 | ~130 |
| 2 | File consolidation | ~600 | ~200 |
| 3 | Parametrization + cleanup | ~150 | ~50 |
| **Total** | | **~750** | **~380** |
| **Net reduction** | | | **~370 lines** |

**Files deleted:** 5
**Files created:** 1 (`tests/helpers.py`)
**Files modified:** ~15
