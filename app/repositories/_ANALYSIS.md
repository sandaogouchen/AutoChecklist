# app/repositories/ Directory Analysis

## §9.1 Directory Overview

The `app/repositories/` directory implements the **data persistence layer** for AutoChecklist. It provides three repository classes that abstract storage concerns behind clean interfaces, allowing the rest of the application to work with domain objects without knowledge of the underlying storage mechanisms.

The directory uses a **dual storage strategy**:

1. **SQLite** (`project_repository.py`) -- For structured, queryable project configuration data that needs relational semantics (CRUD with uniqueness constraints).
2. **Filesystem** (`run_repository.py`, `run_state_repository.py`) -- For run artifacts and state files, organized as per-run directories containing JSON files. This approach leverages the filesystem as a natural organizational structure where each run_id maps to a directory.

**Design Philosophy**: The repositories are intentionally thin wrappers around their storage backends. They handle serialization/deserialization (via Pydantic and JSON) and directory management, but contain no business logic. All domain rules live in the service layer.

---

## §9.2 File Analysis

### §9.2.1 project_repository.py

**Type**: Type B -- Persistence Layer  
**Criticality**: **MEDIUM**  
**Lines**: ~90  
**Primary Export**: `ProjectRepository` class

#### SQLite Persistence Architecture

The `ProjectRepository` uses SQLite as its backend with a single-table schema:

```sql
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

**Key design decisions**:

1. **Schemaless payload storage**: The entire `ProjectContext` Pydantic model is serialized as a JSON string in the `payload` column. This means the SQLite schema does not need to change when `ProjectContext` gains new fields -- only the JSON structure evolves. This is a pragmatic trade-off between query flexibility and schema evolution simplicity.

2. **Default in-memory database**: `db_path=None` defaults to `:memory:`, meaning data is lost on process restart. This is suitable for testing and development but requires explicit file path configuration for persistence.

3. **Thread safety**: `check_same_thread=False` allows the connection to be used from multiple threads, which is necessary when FastAPI handles concurrent requests.

4. **Upsert pattern**: `save()` uses `INSERT ... ON CONFLICT(id) DO UPDATE`, providing idempotent write semantics. A project can be saved repeatedly without checking existence first.

#### CRUD Operations

| Method | SQL Operation | Returns |
|---|---|---|
| `save(project)` | `INSERT ... ON CONFLICT DO UPDATE` | `ProjectContext` |
| `delete(project_id)` | `DELETE WHERE id = ?` | `bool` (existed?) |
| `get(project_id)` | `SELECT WHERE id = ?` | `Optional[ProjectContext]` |
| `list_all()` | `SELECT ORDER BY updated_at DESC, id ASC` | `list[ProjectContext]` |

The `list_all()` ordering (newest first, then alphabetical by ID) provides a sensible default for UI display.

#### Serialization

- **Write**: `json.dumps(project.model_dump(mode="json"))` -- Pydantic v2 serialization
- **Read**: `ProjectContext.model_validate(json.loads(payload))` -- Pydantic v2 deserialization

This pattern ensures type safety at the boundary while storing pure JSON in the database.

#### Path Resolution

`_resolve_db_path()` handles three cases:
1. `None` -> `:memory:` (in-process, ephemeral)
2. String/Path with existing parent directory -> use directly
3. String/Path with non-existent parent -> create parent directories with `mkdir(parents=True, exist_ok=True)`

#### Resource Management

The `close()` method exposes the underlying SQLite connection close. There is no context manager (`__enter__`/`__exit__`) implementation, so callers are responsible for explicit cleanup.

---

### §9.2.2 run_repository.py

**Type**: Type B -- Persistence Layer  
**Criticality**: **MEDIUM**  
**Lines**: ~65  
**Primary Export**: `FileRunRepository` class

#### Filesystem-Based Artifact Storage

The `FileRunRepository` organizes run artifacts in a directory-per-run structure:

```
{root_dir}/
  ├── {run_id_1}/
  │   ├── run_result.json
  │   ├── test_cases.md
  │   └── ... (other artifacts)
  ├── {run_id_2}/
  │   └── ...
  └── ...
```

#### Operations

| Method | Purpose | Returns |
|---|---|---|
| `save(run_id, payload, filename)` | Serialize dict to JSON | `Path` to written file |
| `save_text(run_id, filename, content)` | Write plain text | `Path` to written file |
| `load(run_id, filename)` | Deserialize JSON | `dict[str, Any]` |
| `artifact_path(run_id, filename)` | Get path without I/O | `Path` |

**Default artifact filename**: `run_result.json` -- the primary output of a completed run.

#### Auto-directory creation

`_run_dir(run_id)` calls `ensure_directory()` (from `app/utils/filesystem.py`, §12), which creates the run directory with `mkdir(parents=True, exist_ok=True)`. This means any write operation implicitly creates the directory structure.

#### Delegation to Utils

All file I/O operations delegate to `app.utils.filesystem`:
- `write_json()` for JSON serialization (handles Pydantic models, nested dicts)
- `write_text()` for plain text output
- `read_json()` for deserialization

This keeps the repository focused on directory organization logic while filesystem utilities handle encoding, formatting, and directory creation.

---

### §9.2.3 run_state_repository.py

**Type**: Type B -- Persistence Layer  
**Criticality**: **MEDIUM**  
**Lines**: ~95  
**Primary Export**: `RunStateRepository` class

#### Iterative Evaluation State Persistence

The `RunStateRepository` extends the filesystem storage pattern with awareness of the iterative evaluation loop. It manages three types of state files:

| File | Contents | Updated |
|---|---|---|
| `run_state.json` | Complete `RunState` object | After each iteration |
| `evaluation_report.json` | Latest `EvaluationReport` | After each evaluation |
| `evaluation_report_iter_{N}.json` | Historical evaluation per iteration | When `iteration_index > 0` |
| `iteration_log.json` | Aggregated iteration history and retry decisions | After final iteration |

#### RunState Persistence

```python
def save_run_state(self, run_state: RunState) -> Path
def load_run_state(self, run_id: str) -> RunState
```

Serializes/deserializes the full `RunState` domain object, which includes:
- Current iteration status
- Accumulated test case results
- Evaluation history

#### Evaluation Report Versioning

```python
def save_evaluation_report(self, run_id, report, iteration_index=0) -> Path
```

Dual-write strategy:
1. **Always** writes to `evaluation_report.json` (current/latest version)
2. **When `iteration_index > 0`**: Also writes to `evaluation_report_iter_{N}.json` (historical version)

This allows the system to always find "the latest" evaluation via the unversioned filename, while preserving the complete evaluation history across iterations.

#### Iteration Log

```python
def save_iteration_log(self, run_state: RunState) -> Path
```

Extracts and aggregates iteration metadata from the `RunState`:
```json
{
    "run_id": "...",
    "total_iterations": 3,
    "final_status": "completed",
    "iterations": [...],
    "retry_decisions": [...]
}
```

This provides a human-readable summary of the iterative refinement process.

#### Existence Check

```python
def run_state_exists(self, run_id: str) -> bool
```

Checks for the existence of `run_state.json` without loading it. Used to determine whether a run has been previously started (for resume/skip logic).

---

## §9.3 Data Persistence Architecture

### Storage Strategy Rationale

| Data Type | Storage | Rationale |
|---|---|---|
| Project contexts | SQLite | Need CRUD with uniqueness, ordering, and potential future querying |
| Run artifacts | Filesystem (JSON) | Natural directory-per-run organization, easy inspection, no query needs |
| Run state | Filesystem (JSON) | Part of the run directory, needs versioning per iteration |
| Knowledge index | LightRAG working dir (§13) | Managed by external library |

### Directory Structure (Typical Deployment)

```
{data_root}/
  ├── projects.db              (SQLite, from ProjectRepository)
  └── output/
      └── runs/
          ├── 2026-04-06_14-30-00/     (from run_id generator, §12)
          │   ├── run_result.json       (FileRunRepository)
          │   ├── run_state.json        (RunStateRepository)
          │   ├── evaluation_report.json
          │   ├── evaluation_report_iter_1.json
          │   ├── iteration_log.json
          │   └── test_cases.md
          └── 2026-04-06_14-35-00/
              └── ...
```

### Serialization Strategy

All three repositories use the same serialization pattern:
- **Write**: `model.model_dump(mode="json")` -> `json.dumps()` -> file/DB
- **Read**: file/DB -> `json.loads()` -> `Model.model_validate(data)`

This Pydantic v2-based approach provides:
- Type-safe domain objects in application code
- Human-readable JSON on disk
- Forward-compatible schema evolution (new optional fields automatically handled)

### Concurrency Considerations

- **ProjectRepository**: SQLite with `check_same_thread=False` provides basic thread safety. However, concurrent writes from multiple processes would require WAL mode or external locking.
- **FileRunRepository / RunStateRepository**: Filesystem operations have no explicit locking. Concurrent writes to the same run_id directory could cause corruption. In practice, this is safe because each run_id is unique and processed sequentially.

---

## §9.4 Key Findings

1. **Schemaless JSON-in-SQLite**: The project repository stores entire Pydantic models as JSON blobs. This simplifies schema evolution but prevents SQL-level querying on project attributes (e.g., "find all projects with type=WEB"). If filtering/querying needs grow, the schema may need to be normalized.

2. **No connection pooling**: The `ProjectRepository` creates a single SQLite connection at instantiation. For a single-process FastAPI application this is fine, but scaling to multiple workers would require connection pooling or switching to a server-based database.

3. **No backup/recovery mechanism**: Neither the filesystem repositories nor the SQLite repository have backup, export, or migration capabilities. The `reindex_all()` in the knowledge system (§13) provides a model for how recovery could work.

4. **Implicit directory creation**: Both `FileRunRepository` and `RunStateRepository` auto-create directories on write. This is convenient but means there is no validation that the root directory is writable until the first write attempt.

5. **Evaluation report versioning is sound**: The dual-write pattern (current + historical) for evaluation reports is a well-designed approach for supporting iterative refinement while maintaining easy "latest" access.

6. **No TTL or cleanup**: There is no mechanism to expire or clean up old run directories. Over time, the runs directory could accumulate significant disk usage. A retention policy would be beneficial for production deployments.

7. **Consistent util delegation**: Both filesystem-based repositories delegate I/O operations to `app.utils.filesystem` (§12), maintaining clean separation and avoiding code duplication.

---

## §9.5 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `ProjectContext` | `app/domain/project_models.py` | Domain model stored by ProjectRepository |
| `RunState` | `app/domain/run_state.py` | Domain model stored by RunStateRepository |
| `EvaluationReport` | `app/domain/run_state.py` | Evaluation data stored per iteration |
| `ensure_directory`, `write_json`, `read_json`, `write_text` | `app/utils/filesystem.py` (§12) | File I/O utilities |
| `generate_run_id` | `app/utils/run_id.py` (§12) | Creates the run_id used as directory names |
| `ProjectContextService` | `app/services/project_context_service.py` | Service layer using ProjectRepository |
| `WorkflowService` | `app/services/workflow_service.py` | Service layer using FileRunRepository |
| API layer | `app/api/routes.py` (§3), `app/api/project_routes.py` (§3) | HTTP endpoints delegating to services |
| Knowledge persistence | `app/knowledge/graphrag_engine.py` (§13) | Separate persistence (LightRAG + JSON registry) |