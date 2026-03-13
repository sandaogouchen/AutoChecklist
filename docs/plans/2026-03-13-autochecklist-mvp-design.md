# AutoChecklist MVP Design

**Date:** 2026-03-13

## Goal

Build a runnable MVP API service that reads a local Markdown or PRD file, executes a LangGraph workflow, calls a real LLM API, and returns structured test cases in JSON and Markdown formats. The design must preserve clear extension points for future Feishu document parsing and richer research workflows.

## Scope

### In Scope

- FastAPI-based API service
- One synchronous generation endpoint and one query endpoint
- LangGraph main workflow with a nested case-generation subgraph
- Local Markdown or PRD file parsing
- Real LLM API integration through an OpenAI-compatible client abstraction
- Structured outputs for research and test cases
- Local run artifacts stored under `output/runs/<run_id>/`
- Basic quality checks, deduplication, and result repair
- Automated tests for parser, nodes, workflow, and API

### Out of Scope

- Feishu or Figma live integrations
- Background job queue or database persistence
- Embedding-based semantic clustering
- Multi-agent research orchestration
- Business-template DSL
- Translation or multilingual localization pipeline

## Architecture

The MVP is a FastAPI application with LangGraph as the internal orchestration engine. The HTTP layer is intentionally thin. It validates the request, triggers a workflow run, persists run artifacts locally, and returns a structured response. All business logic lives in parser, node, workflow, and domain layers so the graph can evolve without changing the API surface.

The workflow is organized as one main graph and one subgraph:

1. `InputParserNode`
2. `ContextResearchNode`
3. `CaseGenSubgraph`
4. `ReflectionNode`

The subgraph expands into:

1. `ScenarioPlanner`
2. `EvidenceMapper`
3. `DraftWriter`
4. `StructureAssembler`

This keeps the MVP aligned with the PRD while keeping each node implementation minimal and focused.

## API Design

### `POST /api/v1/case-generation/runs`

Creates and executes one workflow run.

Request body:

- `file_path`: absolute or relative path to a local Markdown or PRD file
- `language`: optional, defaults to `zh-CN`
- `model_config`: optional overrides for model name, temperature, and max tokens
- `options`: optional flags such as `include_intermediate_artifacts`

Response body:

- `run_id`
- `status`
- `input`
- `parsed_document`
- `research_summary`
- `test_cases`
- `quality_report`
- `artifacts`
- `error`

### `GET /api/v1/case-generation/runs/{run_id}`

Returns the latest serialized run result from memory or the artifact directory. This endpoint exists in the MVP even though execution is synchronous so the API remains stable when asynchronous execution is introduced later.

### `GET /healthz`

Returns service health and version metadata.

## Core Data Model

### Domain Objects

- `DocumentSource`: source path, type, title, checksum
- `DocumentSection`: heading, level, content, line range
- `ParsedDocument`: raw text, sections, references, metadata
- `ResearchOutput`: feature topics, user scenarios, constraints, ambiguities, test signals
- `EvidenceRef`: section title, excerpt, line numbers, confidence
- `PlannedScenario`: scenario title, category, risk, rationale
- `TestCase`: id, title, preconditions, steps, expected results, priority, category, evidence refs
- `QualityReport`: duplicate groups, coverage notes, warnings, repaired fields
- `CaseGenerationRun`: API response model and persisted artifact root

### Workflow State

`GlobalState` contains:

- run metadata
- request parameters
- parsed document
- research output
- final test cases
- quality report
- artifact paths
- error metadata

`CaseGenState` contains:

- planned scenarios
- mapped evidence
- draft cases
- assembled cases

This separation keeps the main graph readable while allowing the case-generation logic to stay isolated and testable.

## Node Responsibilities

### InputParserNode

- Validates the file path and extension
- Selects a parser from a parser registry
- Reads and normalizes the file
- Splits the document into structured sections
- Produces a `ParsedDocument`

The parser layer exposes a `BaseDocumentParser` protocol plus a `MarkdownParser` implementation. A future `FeishuParser` can be added without changing graph contracts.

### ContextResearchNode

- Consumes `ParsedDocument`
- Calls the LLM once with a structured research prompt
- Extracts feature topics, scenarios, constraints, ambiguities, and test signals
- Produces `ResearchOutput`

The MVP uses one structured LLM call instead of the full lead-worker research loop. The interface is designed so the internal implementation can later expand into a deeper multi-step research graph.

### CaseGenSubgraph

`ScenarioPlanner`
- Builds candidate test scenarios from research output

`EvidenceMapper`
- Maps each scenario to source sections and excerpts

`DraftWriter`
- Expands scenarios into structured test-case drafts using the LLM

`StructureAssembler`
- Normalizes identifiers, field ordering, and output structure

### ReflectionNode

- Detects rule-based duplicates
- Checks for missing expected results or missing evidence
- Adds warnings and repair notes
- Produces a final `QualityReport`

The MVP keeps reflection lightweight and deterministic. A second LLM repair pass remains an extension point, not a requirement.

## LLM Integration

The service uses an OpenAI-compatible client abstraction configured through environment variables. Required settings:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

Optional settings:

- `LLM_TIMEOUT_SECONDS`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`

Each node interacts with the client through typed request and response helpers. Structured output parsing is enforced with Pydantic models to reduce prompt drift and runtime parsing failures.

## Persistence and Artifacts

Every run writes to `output/runs/<run_id>/`:

- `request.json`
- `parsed_document.json`
- `research_output.json`
- `test_cases.json`
- `test_cases.md`
- `quality_report.json`
- `run_result.json`
- `run.log`

The service keeps a lightweight in-memory run registry for process-local lookups, with local JSON artifacts as the source of truth for later retrieval.

## Error Handling

The MVP distinguishes four error classes:

- request validation errors
- parsing errors
- LLM client errors
- workflow execution errors

All errors are returned in a structured shape with a stable code and message. Each failure also writes a partial artifact bundle to disk so debugging is possible after the HTTP response completes.

## Testing Strategy

### Unit Tests

- markdown parsing and section extraction
- parser registry selection
- deduplication and repair rules
- artifact serialization helpers

### Node Tests

- `ContextResearchNode` with mocked LLM output
- `DraftWriter` with mocked structured responses
- `ReflectionNode` rule checks

### Workflow Tests

- one end-to-end graph execution with a fixture document and mocked LLM client

### API Tests

- `POST /api/v1/case-generation/runs`
- `GET /api/v1/case-generation/runs/{run_id}`
- invalid file-path and invalid extension cases

## Proposed Project Layout

```text
app/
  api/
  clients/
  config/
  domain/
  graphs/
  nodes/
  parsers/
  repositories/
  services/
  utils/
tests/
  fixtures/
  unit/
  integration/
output/
docs/plans/
```

## Open Decisions Resolved for MVP

- Runtime shape: FastAPI service
- Workflow engine: LangGraph from day one
- Input source: local Markdown or PRD files only
- LLM requirement: real API integration required
- Persistence: local artifact directory, no database
- Output: JSON response plus Markdown artifact

## Success Criteria

The MVP is successful when:

1. The API accepts a local Markdown file path and returns structured test cases.
2. The workflow executes through all main graph nodes and the case-generation subgraph.
3. The service calls a real configured LLM endpoint.
4. Artifacts are written locally and a finished run can be queried by `run_id`.
5. Tests cover parser, workflow, and API behavior.
