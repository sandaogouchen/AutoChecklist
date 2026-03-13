# Output Subgraph And Light Response Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move successful run output generation into a dedicated LangGraph output subgraph, split file persistence and platform publishing into child nodes, and shrink the API response to a lightweight summary.

**Architecture:** The main workflow keeps generating `parsed_document`, `research_output`, `test_cases`, and `quality_report`, then hands control to a new `output_delivery` node backed by an internal subgraph. The output subgraph first prepares a typed output bundle, then runs a file-writer node and a platform-writer node; the initial platform writer is a local-file-backed adapter so the publishing contract is decoupled before a real platform integration exists. `WorkflowService` stops writing artifacts directly and returns only a lightweight persisted run summary plus error payloads.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Pydantic v2, pytest

---

### Task 1: Define Lightweight Run Models And Output State

**Files:**
- Create: `app/domain/output_models.py`
- Modify: `app/domain/api_models.py`
- Modify: `app/domain/state.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

```python
from app.domain.api_models import CaseGenerationRunResult
from app.domain.output_models import OutputArtifact, OutputSummary


def test_case_generation_run_result_uses_lightweight_summary() -> None:
    result = CaseGenerationRunResult.model_validate(
        {
            "run_id": "run-1",
            "status": "succeeded",
            "result": {
                "run_id": "run-1",
                "status": "succeeded",
                "test_case_count": 2,
                "warning_count": 1,
                "artifacts": {
                    "run_result": "/tmp/run-1/run_result.json",
                    "test_cases_markdown": "/tmp/run-1/test_cases.md",
                },
                "outputs": [
                    {
                        "key": "test_cases_markdown",
                        "path": "/tmp/run-1/test_cases.md",
                        "kind": "file",
                        "format": "markdown",
                    }
                ],
            },
        }
    )

    assert result.result.test_case_count == 2
    assert result.result.outputs[0].format == "markdown"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_models.py::test_case_generation_run_result_uses_lightweight_summary -v`
Expected: FAIL because `OutputArtifact` / `OutputSummary` do not exist and the response model still expects heavyweight run payloads.

**Step 3: Write minimal implementation**

```python
class OutputArtifact(BaseModel):
    key: str
    path: str
    kind: Literal["file", "platform"]
    format: str


class OutputSummary(BaseModel):
    run_id: str
    status: Literal["succeeded"]
    test_case_count: int = 0
    warning_count: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputArtifact] = Field(default_factory=list)
```

Update `CaseGenerationRunResult.result` to use the new summary model, and extend workflow state with `output_bundle`, `output_summary`, and `artifacts` fields needed by the output subgraph.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/domain/output_models.py app/domain/api_models.py app/domain/state.py tests/unit/test_models.py
git commit -m "feat: add lightweight run summary models"
```

### Task 2: Add A Typed Output Bundle Builder Node

**Files:**
- Create: `app/nodes/output_bundle_builder.py`
- Modify: `app/domain/output_models.py`
- Modify: `app/domain/state.py`
- Test: `tests/unit/test_output_nodes.py`

**Step 1: Write the failing test**

```python
from app.nodes.output_bundle_builder import output_bundle_builder_node


def test_output_bundle_builder_collects_successful_run_payloads() -> None:
    result = output_bundle_builder_node(
        {
            "run_id": "run-1",
            "request": request_fixture,
            "parsed_document": parsed_document_fixture,
            "research_output": research_output_fixture,
            "test_cases": [test_case_fixture],
            "quality_report": quality_report_fixture,
        }
    )

    bundle = result["output_bundle"]
    assert bundle.run_id == "run-1"
    assert "request.json" in bundle.file_payloads
    assert "test_cases.md" in bundle.file_payloads
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py::test_output_bundle_builder_collects_successful_run_payloads -v`
Expected: FAIL because the node and typed bundle do not exist.

**Step 3: Write minimal implementation**

```python
def output_bundle_builder_node(state: GlobalState) -> GlobalState:
    bundle = OutputBundle.from_state(
        run_id=state["run_id"],
        request=state["request"],
        parsed_document=state["parsed_document"],
        research_output=state["research_output"],
        test_cases=state["test_cases"],
        quality_report=state["quality_report"],
    )
    return {"output_bundle": bundle}
```

Include rendered Markdown in the bundle so downstream writer nodes never need to understand test-case structure.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py::test_output_bundle_builder_collects_successful_run_payloads -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/domain/output_models.py app/domain/state.py app/nodes/output_bundle_builder.py tests/unit/test_output_nodes.py
git commit -m "feat: add output bundle builder node"
```

### Task 3: Add File Writer And Decoupled Platform Writer Nodes

**Files:**
- Create: `app/nodes/output_file_writer.py`
- Create: `app/nodes/output_platform_writer.py`
- Modify: `app/repositories/run_repository.py`
- Modify: `app/domain/output_models.py`
- Test: `tests/unit/test_output_nodes.py`

**Step 1: Write the failing tests**

```python
from app.nodes.output_file_writer import build_output_file_writer_node
from app.nodes.output_platform_writer import build_output_platform_writer_node, LocalPlatformPublisher


def test_output_file_writer_persists_bundle_files(tmp_path) -> None:
    node = build_output_file_writer_node(FileRunRepository(tmp_path))
    result = node({"output_bundle": output_bundle_fixture})
    assert (tmp_path / "run-1" / "test_cases.json").exists()
    assert result["artifacts"]["test_cases"] == str(tmp_path / "run-1" / "test_cases.json")


def test_platform_writer_uses_local_adapter_until_real_platform_exists(tmp_path) -> None:
    publisher = LocalPlatformPublisher(root_dir=tmp_path)
    node = build_output_platform_writer_node(publisher)
    result = node({"run_id": "run-1", "output_bundle": output_bundle_fixture})
    assert result["outputs"][-1].kind == "platform"
    assert (tmp_path / "run-1-platform.json").exists()
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py -v`
Expected: FAIL because the writer nodes and publisher contract do not exist.

**Step 3: Write minimal implementation**

```python
class PlatformPublisher(Protocol):
    def publish(self, run_id: str, bundle: OutputBundle) -> OutputArtifact:
        ...


def build_output_file_writer_node(repository: FileRunRepository):
    def output_file_writer_node(state: OutputState) -> OutputState:
        artifacts = repository.save_bundle(state["run_id"], state["output_bundle"])
        return {"artifacts": artifacts}
    return output_file_writer_node
```

Add `FileRunRepository.save_bundle(...)` so file-writing logic lives behind one repository method, and implement `LocalPlatformPublisher` as a local JSON emitter that simulates platform delivery without coupling the graph to a real platform client.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/nodes/output_file_writer.py app/nodes/output_platform_writer.py app/repositories/run_repository.py app/domain/output_models.py tests/unit/test_output_nodes.py
git commit -m "feat: add output writer nodes"
```

### Task 4: Build The Output Delivery Subgraph And Wire It Into The Main Workflow

**Files:**
- Create: `app/graphs/output_delivery.py`
- Modify: `app/graphs/main_workflow.py`
- Modify: `app/services/workflow_service.py`
- Test: `tests/integration/test_workflow.py`

**Step 1: Write the failing test**

```python
def test_workflow_writes_outputs_via_output_delivery_subgraph(tmp_path, fake_llm_client) -> None:
    workflow = build_workflow(
        fake_llm_client,
        repository=FileRunRepository(tmp_path),
        platform_publisher=LocalPlatformPublisher(tmp_path),
    )

    result = workflow.invoke(
        {
            "run_id": "run-1",
            "file_path": str(Path("tests/fixtures/sample_prd.md").resolve()),
            "language": "zh-CN",
            "request": CaseGenerationRequest(file_path=str(Path("tests/fixtures/sample_prd.md").resolve())),
        }
    )

    assert result["output_summary"].test_case_count == 1
    assert (tmp_path / "run-1" / "run_result.json").exists()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_workflow.py::test_workflow_writes_outputs_via_output_delivery_subgraph -v`
Expected: FAIL because the workflow has no output node and `build_workflow` does not accept output dependencies.

**Step 3: Write minimal implementation**

```python
def build_workflow(llm_client: LLMClient, repository: FileRunRepository, platform_publisher: PlatformPublisher | None = None):
    output_subgraph = build_output_delivery_subgraph(
        repository=repository,
        platform_publisher=platform_publisher or LocalPlatformPublisher(repository.root_dir),
    )
    builder.add_node("output_delivery", _build_output_delivery_node(output_subgraph))
    builder.add_edge("reflection", "output_delivery")
    builder.add_edge("output_delivery", END)
```

Remove direct artifact persistence from `WorkflowService`; after this change the service should only invoke the workflow, translate success results into `CaseGenerationRunResult`, and cache the lightweight summary.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/graphs/output_delivery.py app/graphs/main_workflow.py app/services/workflow_service.py tests/integration/test_workflow.py
git commit -m "feat: add output delivery subgraph"
```

### Task 5: Shrink POST/GET Responses And Remove Failure-Path Output Files

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/services/workflow_service.py`
- Modify: `app/domain/api_models.py`
- Test: `tests/integration/test_api.py`

**Step 1: Write the failing tests**

```python
def test_create_run_returns_lightweight_summary(tmp_path, fake_llm_client) -> None:
    response = client.post("/api/v1/case-generation/runs", json={"file_path": fixture_path})
    payload = response.json()

    assert payload["status"] == "succeeded"
    assert "parsed_document" not in payload["result"]
    assert "test_cases" not in payload["result"]
    assert payload["result"]["test_case_count"] == 1
    assert "run_result" in payload["result"]["artifacts"]


def test_failed_run_does_not_create_output_directory(tmp_path) -> None:
    response = client.post("/api/v1/case-generation/runs", json={"file_path": fixture_path})
    payload = response.json()

    assert payload["status"] == "failed"
    assert not any(tmp_path.iterdir())
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/integration/test_api.py -v`
Expected: FAIL because the API still returns heavyweight result data and `WorkflowService` still writes files outside the graph path.

**Step 3: Write minimal implementation**

```python
def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRunResult:
    run_id = uuid4().hex
    try:
        result = self._get_workflow().invoke({...})
        summary = result["output_summary"]
        run = CaseGenerationRunResult(
            run_id=run_id,
            status="succeeded",
            result=summary,
        )
    except Exception as exc:
        run = CaseGenerationRunResult(
            run_id=run_id,
            status="failed",
            error=ErrorInfo(code=exc.__class__.__name__, message=str(exc)),
        )
```

Delete the eager `request.json` write at the top of `create_run`; `request.json` must now be emitted only by the success-path file writer node.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/integration/test_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/routes.py app/services/workflow_service.py app/domain/api_models.py tests/integration/test_api.py
git commit -m "feat: return lightweight run summaries"
```

### Task 6: Persist A Lightweight `run_result.json` And Document The New Contract

**Files:**
- Modify: `app/nodes/output_file_writer.py`
- Modify: `README.md`
- Modify: `tests/integration/test_api.py`
- Modify: `tests/unit/test_run_repository.py`

**Step 1: Write the failing tests**

```python
def test_run_result_json_contains_summary_only(tmp_path) -> None:
    payload = read_json(tmp_path / "run-1" / "run_result.json")
    assert payload["result"]["test_case_count"] == 1
    assert "test_cases" not in payload["result"]
    assert "parsed_document" not in payload["result"]
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_run_repository.py tests/integration/test_api.py -v`
Expected: FAIL because `run_result.json` still mirrors the heavyweight internal run model or is written by the service.

**Step 3: Write minimal implementation**

```python
summary_payload = CaseGenerationRunResult(
    run_id=run_id,
    status="succeeded",
    result=state["output_summary"],
).model_dump(mode="json", by_alias=True)
repository.save(run_id, summary_payload, "run_result.json")
```

Update README examples to show the lightweight response and explicitly document the new success-only output directory behavior.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_run_repository.py tests/integration/test_api.py tests/integration/test_workflow.py tests/unit/test_output_nodes.py tests/unit/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/nodes/output_file_writer.py README.md tests/unit/test_run_repository.py tests/integration/test_api.py
git commit -m "docs: describe lightweight output contract"
```

### Task 7: Run Full Regression And Check Contract Edges

**Files:**
- Modify: `tests/unit/test_nodes.py`
- Modify: `tests/unit/test_llm_client.py`
- Modify: `docs/plans/2026-03-14-output-subgraph-light-response.md`

**Step 1: Add focused regression tests**

```python
def test_get_run_returns_lightweight_summary_from_disk(...) -> None:
    ...


def test_failed_run_is_only_available_in_memory_until_restart(...) -> None:
    ...
```

**Step 2: Run the targeted regressions**

Run: `.venv/bin/pytest tests/unit/test_nodes.py tests/unit/test_llm_client.py tests/unit/test_models.py tests/unit/test_output_nodes.py tests/unit/test_run_repository.py tests/integration/test_workflow.py tests/integration/test_api.py -v`
Expected: PASS

**Step 3: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS

**Step 4: Record any follow-up contract caveats**

Document in this plan and README that:
- failed runs do not create output directories
- cross-process `GET /runs/{run_id}` is guaranteed only for successful runs
- real platform publishing should replace `LocalPlatformPublisher` without changing the output subgraph contract

**Step 5: Commit**

```bash
git add tests/unit/test_nodes.py tests/unit/test_llm_client.py tests/unit/test_models.py tests/unit/test_output_nodes.py tests/unit/test_run_repository.py tests/integration/test_workflow.py tests/integration/test_api.py README.md docs/plans/2026-03-14-output-subgraph-light-response.md
git commit -m "test: verify output subgraph contract"
```

### Contract Caveats Recorded

- Failed runs do not create output directories.
- Cross-process `GET /api/v1/case-generation/runs/{run_id}` is guaranteed only for successful runs because only successful summaries are persisted to disk.
- `LocalPlatformPublisher` is a temporary adapter. A real platform publisher should preserve the `PlatformPublisher` contract and the `output_delivery` subgraph shape.
