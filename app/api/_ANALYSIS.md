# app/api/ Directory Analysis

## §3.1 Directory Overview

The `app/api/` directory implements the HTTP REST API layer for the AutoChecklist system using FastAPI. It contains three router modules that collectively expose endpoints for:

1. **Core workflow operations** (`routes.py`) -- health checks, case generation run creation/retrieval, and template management.
2. **Project context CRUD** (`project_routes.py`) -- full lifecycle management of project configurations that influence test case generation.
3. **Knowledge base management** (`knowledge_routes.py`) -- document indexing, retrieval, and status management for the GraphRAG-powered knowledge system.

**Technology**: FastAPI with `APIRouter`, Pydantic v2 request/response models, and dependency injection via `Depends()` pulling shared service instances from `request.app.state`.

**Architectural Role**: The API layer is a thin adapter -- it handles HTTP concerns (validation, error mapping, serialization) and delegates all business logic to service-layer objects (`WorkflowService`, `ProjectContextService`, `GraphRAGEngine`). No domain logic resides in the route handlers.

---

## §3.2 File Analysis

### §3.2.1 routes.py

**Type**: Type B -- API Adapter  
**Lines**: ~120  
**Router prefix**: None (root-level)  
**Endpoints**: 5

#### Endpoint Inventory

| Method | Path | Handler | Response Model | Purpose |
|---|---|---|---|---|
| `GET` | `/healthz` | `healthz()` | `dict[str, str]` | Health check with app name and version |
| `POST` | `/api/v1/case-generation/runs` | `create_case_generation_run()` | `CaseGenerationRun` | Create and synchronously execute a case generation run |
| `GET` | `/api/v1/case-generation/runs/{run_id}` | `get_case_generation_run()` | `CaseGenerationRun` | Retrieve a completed run by ID |
| `GET` | `/api/v1/templates` | `list_templates()` | `list[dict[str, str]]` | List available project templates |
| `GET` | `/api/v1/templates/{name}` | `get_template()` | `dict` | Get specific template details |

#### Dependency Injection Pattern

Two helper functions retrieve shared state from `request.app.state`:

- `_get_settings(request)` -> `Settings` -- global application configuration
- `_get_workflow_service(request)` -> `WorkflowService` -- the service that orchestrates workflow execution

This pattern ensures the API layer and workflow layer share the same service instances, avoiding duplicate initialization.

#### Synchronous Execution Model

**Critical design note**: The `POST /api/v1/case-generation/runs` endpoint executes the workflow **synchronously** -- the HTTP request blocks until the entire LangGraph pipeline completes. Given that the pipeline includes multiple LLM calls (context_research, checkpoint_generator, checkpoint_outline_planner, draft_writer), this can take significant time (30s-5min depending on document size and LLM latency).

The `create_case_generation_run()` handler directly calls `workflow_service.create_run(payload)` and returns the full `CaseGenerationRun` result. There is no background task queue, no WebSocket progress reporting, and no async polling pattern.

#### Template Management

The template endpoints scan the filesystem (`settings.template_dir`) for YAML files, loading each through `ProjectTemplateLoader`. Error handling is per-file: a single corrupt template file produces a warning log but does not prevent listing other templates.

The `get_template()` endpoint distinguishes between `FileNotFoundError` (404) and `TemplateValidationError` (422), providing appropriate HTTP status codes.

#### Error Handling

- `FileNotFoundError` from `workflow_service.get_run()` maps to HTTP 404
- Template loading errors are caught per-file during listing (logged, not surfaced)
- Template validation errors map to HTTP 422

---

### §3.2.2 project_routes.py

**Type**: Type B -- API Adapter  
**Lines**: ~100  
**Router prefix**: `/projects`  
**Tag**: `projects`  
**Endpoints**: 5

#### CRUD Endpoint Inventory

| Method | Path | Handler | Status | Purpose |
|---|---|---|---|---|
| `POST` | `/projects` | `create_project()` | 201 | Create a new project context |
| `GET` | `/projects` | `list_projects()` | 200 | List all projects |
| `GET` | `/projects/{project_id}` | `get_project()` | 200 | Get specific project |
| `PATCH` | `/projects/{project_id}` | `update_project()` | 200 | Partial update (exclude_unset) |
| `DELETE` | `/projects/{project_id}` | `delete_project()` | 204 | Delete a project |

#### Request/Response Models

Two Pydantic models defined inline:

- **`ProjectCreateRequest`**: Required `name` (1-200 chars), optional `description` (max 5000), `project_type` (enum, defaults to `OTHER`), `regulatory_frameworks` (list of enums), `tech_stack`, `custom_standards`, `metadata` dict.
- **`ProjectUpdateRequest`**: All fields optional (for PATCH semantics). Uses `model_dump(exclude_unset=True)` to distinguish "field not provided" from "field set to None".

#### Domain Model Integration

The route handlers delegate to `ProjectContextService` and use domain enums:
- `ProjectType` -- categorizes the project (e.g., web, mobile, OTHER)
- `RegulatoryFramework` -- applicable compliance frameworks

Responses are serialized via `project.model_dump()` rather than using a dedicated response model, returning the full `ProjectContext` domain object as JSON.

#### Error Handling

- `get_project()`: Returns 404 if `svc.get_project()` returns `None`
- `update_project()`: Catches `KeyError` from service layer, maps to 404
- `delete_project()`: Returns 404 if `svc.delete_project()` returns `False`

---

### §3.2.3 knowledge_routes.py

**Type**: Type B -- API Adapter  
**Lines**: ~150  
**Router prefix**: `/api/v1/knowledge`  
**Tag**: `knowledge`  
**Endpoints**: 6

#### Endpoint Inventory

| Method | Path | Handler | Async | Purpose |
|---|---|---|---|---|
| `POST` | `/documents` | `upload_document()` | Yes | Upload and index a Markdown knowledge document |
| `GET` | `/documents` | `list_documents()` | Yes | List all indexed documents |
| `DELETE` | `/documents/{doc_id}` | `delete_document()` | Yes | Delete a specific document |
| `POST` | `/query` | `query_knowledge()` | Yes | Manual knowledge base query (debug) |
| `POST` | `/reindex` | `reindex_knowledge()` | Yes | Trigger full index rebuild |
| `GET` | `/status` | `get_knowledge_status()` | Yes | Get knowledge system status |

#### Async Design

All knowledge endpoints are `async def`, reflecting the async nature of the `GraphRAGEngine` (which uses `ainsert`, `aquery`, etc.). This is the only router module using async handlers.

#### Engine Dependency

The `_get_engine()` dependency retrieves `GraphRAGEngine` from `app.state` and raises HTTP 503 ("知识检索功能未启用或引擎未初始化") if the engine is not available. This graceful degradation allows the application to run without the knowledge feature.

#### Document Upload Flow

1. Validate file path via `validate_document_path()` (checks existence, .md extension, size limit, UTF-8 encoding)
2. Resolve absolute path
3. Call `engine.insert_document(content, metadata)` for LightRAG indexing
4. Return `DocumentUploadResponse` with `doc_id`, `file_name`, `status`, `entity_count`

Notable: The upload accepts a **local file path** (not a multipart upload). This implies the knowledge documents must already exist on the server's filesystem.

#### Request/Response Models

Dedicated Pydantic models for each operation:
- `DocumentUploadRequest` / `DocumentUploadResponse`
- `KnowledgeQueryRequest` (with `mode` field: naive/local/global/hybrid/mix) / `KnowledgeQueryResponse`
- `ReindexResponse`
- `KnowledgeStatus` (imported from domain models)

#### Error Handling

| Scenario | HTTP Status | Detail |
|---|---|---|
| Engine not initialized | 503 | "知识检索功能未启用或引擎未初始化" |
| Invalid file path | 400 | Validation error message |
| Insert runtime error | 503 | Runtime error message |
| Document not found | 404 | "文档未找到: {doc_id}" |
| Query failure | 500 | Error message from result |
| Reindex failure | 500 | Exception message |

---

## §3.3 API Design Analysis

### Versioning Strategy

- Core endpoints use `/api/v1/` prefix (routes.py, knowledge_routes.py)
- Project endpoints use bare `/projects` prefix (no version prefix)
- Health check at root `/healthz`

This inconsistency in versioning between `routes.py`/`knowledge_routes.py` (versioned) and `project_routes.py` (unversioned) may cause issues if API versioning becomes necessary.

### Authentication & Authorization

No authentication or authorization mechanisms are visible in any of the three router modules. There are no auth dependencies, no token validation, no role-based access control. This is appropriate for an internal tool but would need attention for any external deployment.

### Sync vs. Async Inconsistency

- `routes.py` and `project_routes.py` use synchronous handlers (`def`)
- `knowledge_routes.py` uses async handlers (`async def`)

This is functionally correct (FastAPI handles both), but the sync `create_case_generation_run` endpoint is potentially problematic -- it blocks a thread pool worker for the entire duration of the LLM pipeline.

### Shared State Pattern

All three routers use `request.app.state` as a service locator:
- `request.app.state.settings` -- `Settings`
- `request.app.state.workflow_service` -- `WorkflowService`
- `request.app.state.project_context_service` -- `ProjectContextService`
- `request.app.state.graphrag_engine` -- `GraphRAGEngine`

This is a lightweight dependency injection pattern suitable for a single-process application but would need reworking for multi-process deployments.

---

## §3.4 Key Findings

1. **Synchronous workflow execution**: The most significant architectural concern is that `POST /api/v1/case-generation/runs` blocks until the entire pipeline completes. For complex documents with multiple LLM calls, this can exceed typical HTTP timeout thresholds. There is no async task queue or progress callback mechanism.

2. **File-path-based knowledge upload**: The knowledge document upload accepts a server-local file path rather than a file upload. This limits the API's usability from external clients and couples the API to the server's filesystem.

3. **Inconsistent API versioning**: Project routes lack the `/api/v1/` prefix used by other routes, creating an inconsistency that could complicate future API evolution.

4. **No authentication**: All endpoints are unauthenticated, appropriate for internal use but a gap for any broader deployment.

5. **Graceful knowledge degradation**: The knowledge routes properly handle the case where the GraphRAG engine is not initialized, returning 503 rather than crashing. This allows the application to function without the knowledge feature.

6. **Response model inconsistency**: Project routes return raw `model_dump()` dicts rather than using typed response models, while other routes use Pydantic response models. This reduces type safety in the project API.

---

## §3.5 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `Settings` | `app/config/settings.py` | Global configuration |
| `WorkflowService` | `app/services/workflow_service.py` | Workflow orchestration (invokes graphs §6) |
| `CaseGenerationRequest/Run` | `app/domain/api_models.py` | API request/response models |
| `ProjectContextService` | `app/services/project_context_service.py` | Project CRUD business logic |
| `ProjectContext` | `app/domain/project_models.py` | Project domain model |
| `ProjectType`, `RegulatoryFramework` | `app/domain/project_models.py` | Domain enums |
| `GraphRAGEngine` | `app/knowledge/graphrag_engine.py` (§13) | Knowledge retrieval engine |
| `validate_document_path` | `app/knowledge/ingestion.py` (§13) | Document validation |
| `KnowledgeDocument`, `KnowledgeStatus` | `app/knowledge/models.py` (§13) | Knowledge domain models |
| `ProjectTemplateLoader` | `app/services/template_loader.py` | Template loading service |
| `build_workflow()` | `app/graphs/main_workflow.py` (§6) | Called indirectly via WorkflowService |