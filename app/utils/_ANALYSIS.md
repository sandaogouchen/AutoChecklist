# app/utils/ Directory Analysis

## §12.1 Directory Overview

The `app/utils/` directory provides **shared utility infrastructure** used across multiple layers of the AutoChecklist system. It contains three focused modules:

1. **`filesystem.py`** -- Core file I/O primitives (directory creation, JSON read/write, text write) used by all repository classes and other modules needing filesystem access.
2. **`run_id.py`** -- UTC+8 timestamp-based run identifier generation with conflict detection, used to create unique, human-readable run directory names.
3. **`timing.py`** -- Node-level execution timing infrastructure for the LangGraph pipeline, providing non-invasive profiling of workflow nodes.

**Design Philosophy**: These utilities are stateless, side-effect-contained functions and classes. They have no domain knowledge -- they provide generic capabilities that any module can use. The exception is `timing.py`, which has some awareness of LangGraph node conventions and known LLM-calling node names.

---

## §12.2 File Analysis

### §12.2.1 filesystem.py

**Type**: Type C -- Infrastructure Utility  
**Criticality**: **MEDIUM** (foundational, used by all repositories)  
**Lines**: ~65  
**Primary Exports**: `ensure_directory()`, `write_json()`, `read_json()`, `write_text()`

#### Function Inventory

| Function | Purpose | Key Behavior |
|---|---|---|
| `ensure_directory(path)` | Create directory (recursive) | `mkdir(parents=True, exist_ok=True)`, returns `Path` |
| `write_json(path, payload)` | Serialize and write JSON | Auto-creates parent dirs, handles Pydantic models |
| `read_json(path)` | Read and deserialize JSON | Raises `FileNotFoundError` / `JSONDecodeError` |
| `write_text(path, content)` | Write plain text | Auto-creates parent dirs, UTF-8 encoding |

#### Pydantic-Aware JSON Serialization

The internal `_to_jsonable(payload)` function recursively converts payloads to JSON-serializable types:

```python
def _to_jsonable(payload):
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _to_jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_to_jsonable(item) for item in payload]
    return payload
```

This handles:
- **Pydantic BaseModel instances** -> converted via `model_dump(mode="json")`
- **Nested dicts** -> recursively process values
- **Lists** -> recursively process elements
- **Primitives** -> pass through to `json.dumps()`

The `mode="json"` parameter ensures Pydantic uses JSON-compatible types (e.g., `datetime` -> ISO string, `Enum` -> value).

#### JSON Formatting

`write_json()` uses `json.dumps(..., ensure_ascii=False, indent=2)`:
- `ensure_ascii=False` -- preserves Chinese characters as-is (critical for this project's Chinese-language output)
- `indent=2` -- human-readable formatting (important for debugging run artifacts)

#### Error Handling Strategy

- **Write operations**: Implicitly raise `OSError` on permission/disk issues (no catch/wrap)
- **Read operations**: `read_json()` propagates `FileNotFoundError` and `json.JSONDecodeError` without wrapping
- This is intentional -- callers are expected to handle storage errors at the appropriate level

---

### §12.2.2 run_id.py

**Type**: Type C -- Infrastructure Utility  
**Criticality**: **LOW-MEDIUM**  
**Lines**: ~55  
**Primary Export**: `generate_run_id()` function

#### ID Format and Generation

```
Format: YYYY-MM-DD_HH-mm-ss
Example: 2026-04-06_14-30-00
```

The run_id serves dual purposes:
1. **Unique identifier** for API responses and internal references
2. **Directory name** under `output/runs/` for artifact storage

#### Timezone Handling

Uses `zoneinfo.ZoneInfo("Asia/Shanghai")` (UTC+8) explicitly, not the system default timezone. This ensures:
- Consistent IDs regardless of server timezone setting
- Human-readable timestamps in the team's local timezone
- Deterministic behavior across different deployment environments

#### Conflict Resolution Strategy

```
1. Try base ID: "2026-04-06_14-30-00"
2. If exists: try "2026-04-06_14-30-00_2"
3. If exists: try "2026-04-06_14-30-00_3"
   ...
100. If exists: try "2026-04-06_14-30-00_101"
101. Fallback: use UUID hex (32 characters)
```

The conflict check uses `(root / candidate).exists()` -- a filesystem existence check on the target directory path. The sequential numbering provides human-readable disambiguation for rapid successive runs, while the UUID fallback ensures uniqueness under extreme conditions.

**`_MAX_CONFLICT_RETRIES = 100`**: This limit is generous -- hitting it would require 100+ runs within the same second, which is implausible in normal operation. The UUID fallback logs a warning, signaling an unusual condition.

#### Edge Cases

- Multiple workers generating IDs simultaneously could race, but the filesystem existence check provides eventual uniqueness (at worst, two workers might skip the same suffix and both get unique IDs)
- The UUID fallback breaks the timestamp-based naming convention but maintains uniqueness

---

### §12.2.3 timing.py

**Type**: Type B -- Observability Infrastructure  
**Criticality**: **MEDIUM**  
**Lines**: ~280  
**Primary Exports**: `NodeTimer`, `TimingRecord`, `wrap_node()`, `maybe_wrap()`, `log_timing_report()`

#### Architecture Overview

The timing module provides a **non-invasive profiling system** for LangGraph workflow nodes. It wraps individual node functions to measure execution time without modifying the node implementations.

```
[Node Function] → wrap_node() → [Wrapped Function]
                                     │
                                     ├─ Records start time
                                     ├─ Calls original function
                                     ├─ Records end time
                                     ├─ Stores TimingRecord in NodeTimer
                                     └─ Logs timing info
```

#### TimingRecord Dataclass

| Field | Type | Purpose |
|---|---|---|
| `node_name` | `str` | Node identifier |
| `elapsed_seconds` | `float` | Wall-clock execution time |
| `is_llm_node` | `bool` | Whether this node contains LLM calls |
| `iteration_index` | `int` | Which iteration this timing belongs to |
| `timestamp_start` | `str` | ISO UTC timestamp at start |
| `timestamp_end` | `str` | ISO UTC timestamp at end |
| `had_error` | `bool` | Whether the node raised an exception |
| `is_internal` | `bool` | Whether this is an infrastructure record |

#### NodeTimer Class

A mutable container that accumulates `TimingRecord` entries with filtering and aggregation capabilities:

**Recording**: `record(name, elapsed, is_llm_node, ...)` appends a new `TimingRecord`

**Retrieval**:
- `get_records(iteration_index, include_internal)` -- filtered record access
- `get_all_records()` -- unfiltered access
- `total_seconds(iteration_index)` -- sum of non-internal elapsed times
- `llm_seconds(iteration_index)` -- sum of LLM node elapsed times

**Export**: `to_dict()` produces a serializable summary:
```json
{
    "iterations": {"0": [...records...], "1": [...records...]},
    "internal": [...internal records...],
    "total_pipeline_seconds": 45.2,
    "total_llm_nodes_seconds": 38.7,
    "llm_ratio": 0.856
}
```

The `llm_ratio` metric is particularly valuable -- it shows what fraction of pipeline time is spent on LLM calls, which is typically the dominant cost factor.

#### LLM Node Auto-Detection

```python
_LLM_NODE_NAMES: frozenset[str] = frozenset({
    "context_research",
    "checkpoint_generator",
    "checkpoint_outline_planner",
    "draft_writer",
})
```

When `is_llm_node=None` (default), `wrap_node()` automatically checks this set to classify nodes. This hardcoded set must be kept in sync with actual LLM-calling nodes in the pipeline, which is a maintenance concern (new LLM nodes could be missed).

**Notably missing**: `mr_analyzer` is an LLM-calling node (§6.2.2) but is not in this set. This means MR analysis time is not tracked as LLM time in the profiling reports.

#### `wrap_node()` Implementation

```python
def wrap_node(name, fn, timer, is_llm_node=None, iteration_index=0):
    @functools.wraps(fn)
    def wrapper(state):
        ts_start = _now_iso()
        start = time.monotonic()
        had_error = False
        try:
            result = fn(state)
            return result
        except Exception:
            had_error = True
            raise
        finally:
            elapsed = time.monotonic() - start
            # ... record timing ...
    return wrapper
```

Key design points:
- Uses `time.monotonic()` for elapsed time (immune to system clock changes)
- `functools.wraps(fn)` preserves the original function's metadata
- Error tracking via `finally` block -- timing is recorded even on failure
- Uses a dedicated `timing_logger` (named `app.timing`) for timing-specific log output

#### `maybe_wrap()` Convenience

```python
def maybe_wrap(name, fn, timer, iteration_index):
    if timer is None:
        return fn
    return wrap_node(name, fn, timer, iteration_index=iteration_index)
```

This is used extensively in both `main_workflow.py` and `case_generation.py` (§6) when adding nodes to the graph builder. It allows timer to be optional without littering the graph construction code with conditional checks.

#### `log_timing_report()` Reporting

Produces a formatted console report:

```
[TIMING] ═══ Timing Report (iteration 0) ═══
[TIMING] input_parser                    :     0.12s
[TIMING] template_loader                 :     0.05s
[TIMING] context_research                :    12.34s  ⚠ LLM
[TIMING] checkpoint_generator            :    15.67s  ⚠ LLM
[TIMING] ──────────────────────────────────────────────
[TIMING] Total pipeline                  :    45.20s
[TIMING] Total LLM nodes                 :    38.70s (85.6%)
[TIMING] ══════════════════════════════════════════════
```

Also returns a serializable dict with the same data for persistence in run artifacts.

---

## §12.3 Key Findings

1. **Chinese character preservation**: The `ensure_ascii=False` in `write_json()` is essential for this project, which generates Chinese-language test cases. Without it, all Chinese text would be escaped to `\uXXXX` sequences in the JSON files, making them unreadable.

2. **UTC+8 hardcoded timezone**: The run_id generator uses a hardcoded `Asia/Shanghai` timezone. This is appropriate for the current team but would need parameterization for global deployment.

3. **Missing LLM node in timing set**: `mr_analyzer` performs LLM calls but is not in `_LLM_NODE_NAMES`. This means timing reports under-report the LLM ratio when MR analysis is active. The `build_coco_consistency_validator_node` and `checkpoint_outline_planner` (which is listed) are other nodes worth verifying.

4. **No async timing support**: `wrap_node()` only handles synchronous node functions. If any node were to become async (e.g., the knowledge retrieval node), the timing wrapper would need an async variant.

5. **Race condition in run_id generation**: Under concurrent requests, two threads could check the same directory, find it doesn't exist, and both generate the same run_id. In practice, the filesystem `mkdir` call in downstream code would cause one to succeed and the other to get a directory that already exists (harmless with `exist_ok=True`), but the two runs would share the same directory, which would be problematic. The synchronous endpoint model (§3) makes this unlikely in the current architecture.

6. **Internal record separation**: The timing system distinguishes between regular node records and "internal" records (like workflow-level overhead). This prevents infrastructure overhead from inflating per-node timing metrics -- a thoughtful design for accurate profiling.

7. **Monotonic time is correct**: Using `time.monotonic()` instead of `time.time()` ensures elapsed time measurements are not affected by NTP adjustments or system clock changes. This is a best practice for performance measurement.

---

## §12.4 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `ensure_directory` used by | `app/repositories/run_repository.py` (§9) | Directory creation for run artifacts |
| `write_json`, `read_json` used by | `app/repositories/run_repository.py` (§9) | JSON artifact I/O |
| `write_json`, `read_json` used by | `app/repositories/run_state_repository.py` (§9) | State persistence I/O |
| `write_text` used by | `app/repositories/run_repository.py` (§9) | Text artifact output |
| `generate_run_id` used by | `app/services/workflow_service.py` | Run identifier creation |
| `NodeTimer` used by | `app/graphs/main_workflow.py` (§6) | Main workflow timing |
| `NodeTimer` used by | `app/graphs/case_generation.py` (§6) | Sub-graph timing |
| `maybe_wrap` used by | `app/graphs/main_workflow.py` (§6) | Conditional node wrapping |
| `maybe_wrap` used by | `app/graphs/case_generation.py` (§6) | Conditional node wrapping |
| `log_timing_report` used by | `app/services/workflow_service.py` | Report generation after run |
| Timing data persisted by | `app/repositories/run_repository.py` (§9) | Saved as run artifact |
