# AutoChecklist MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a runnable FastAPI service that reads a local Markdown or PRD file, executes a LangGraph workflow backed by a real OpenAI-compatible LLM API, and returns structured test cases plus local output artifacts.

**Architecture:** The system is a FastAPI API layer over a LangGraph main workflow with one nested case-generation subgraph. Parser, node, client, and repository layers are separated so the MVP supports only Markdown today but can add Feishu parsing and deeper research flows later without changing the API contract.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, LangGraph, LangChain Core, Pydantic v2, pytest, httpx, respx or unittest.mock

---

### Task 1: Scaffold project structure and Python package

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/api/__init__.py`
- Create: `app/api/routes.py`
- Create: `app/config/__init__.py`
- Create: `app/config/settings.py`
- Create: `tests/__init__.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_health.py -v`
Expected: FAIL with import or module-not-found errors because the application package does not exist yet.

**Step 3: Write minimal implementation**

Create a minimal FastAPI app with a `/healthz` route, base package files, and a `Settings` model that loads environment variables for the API service.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_health.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml README.md app tests
git commit -m "chore: scaffold FastAPI service"
```

### Task 2: Define request, response, and domain models

**Files:**
- Create: `app/domain/__init__.py`
- Create: `app/domain/api_models.py`
- Create: `app/domain/document_models.py`
- Create: `app/domain/research_models.py`
- Create: `app/domain/case_models.py`
- Create: `app/domain/state.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

```python
from app.domain.api_models import CaseGenerationRequest


def test_case_generation_request_defaults_language():
    request = CaseGenerationRequest(file_path="prd.md")
    assert request.language == "zh-CN"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL because the domain models do not exist yet.

**Step 3: Write minimal implementation**

Add Pydantic models for API payloads, parsed documents, research output, test cases, quality reports, and the LangGraph states.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/domain tests/unit/test_models.py
git commit -m "feat: add workflow domain models"
```

### Task 3: Build the parser abstraction and Markdown parser

**Files:**
- Create: `app/parsers/__init__.py`
- Create: `app/parsers/base.py`
- Create: `app/parsers/markdown.py`
- Create: `app/parsers/factory.py`
- Test: `tests/unit/test_markdown_parser.py`
- Create: `tests/fixtures/sample_prd.md`

**Step 1: Write the failing test**

```python
from pathlib import Path

from app.parsers.factory import get_parser


def test_markdown_parser_extracts_sections():
    parser = get_parser(Path("tests/fixtures/sample_prd.md"))
    parsed = parser.parse(Path("tests/fixtures/sample_prd.md"))
    assert parsed.sections
    assert parsed.sections[0].heading
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_markdown_parser.py -v`
Expected: FAIL because no parser implementation exists.

**Step 3: Write minimal implementation**

Define a parser protocol, implement a Markdown parser that reads headings into structured sections with line ranges, and add a parser factory that currently selects only the Markdown parser.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_markdown_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/parsers tests/unit/test_markdown_parser.py tests/fixtures/sample_prd.md
git commit -m "feat: add markdown parser"
```

### Task 4: Implement the LLM client abstraction

**Files:**
- Create: `app/clients/__init__.py`
- Create: `app/clients/llm.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: Write the failing test**

```python
from app.clients.llm import LLMClientConfig


def test_llm_config_requires_api_key():
    try:
        LLMClientConfig(api_key="", base_url="https://example.com", model="test-model")
    except ValueError:
        assert True
    else:
        assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: FAIL because the LLM client module does not exist.

**Step 3: Write minimal implementation**

Create an OpenAI-compatible LLM client wrapper with config validation and a typed method for structured JSON generation.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/clients tests/unit/test_llm_client.py
git commit -m "feat: add openai-compatible llm client"
```

### Task 5: Implement workflow node functions

**Files:**
- Create: `app/nodes/__init__.py`
- Create: `app/nodes/input_parser.py`
- Create: `app/nodes/context_research.py`
- Create: `app/nodes/scenario_planner.py`
- Create: `app/nodes/evidence_mapper.py`
- Create: `app/nodes/draft_writer.py`
- Create: `app/nodes/structure_assembler.py`
- Create: `app/nodes/reflection.py`
- Test: `tests/unit/test_nodes.py`

**Step 1: Write the failing test**

```python
from app.nodes.reflection import deduplicate_cases
from app.domain.case_models import TestCase


def test_deduplicate_cases_removes_identical_titles():
    case_a = TestCase(id="TC-1", title="Login succeeds", preconditions=[], steps=["A"], expected_results=["B"], priority="P1", category="normal", evidence_refs=[])
    case_b = TestCase(id="TC-2", title="Login succeeds", preconditions=[], steps=["A"], expected_results=["B"], priority="P1", category="normal", evidence_refs=[])
    deduped, report = deduplicate_cases([case_a, case_b])
    assert len(deduped) == 1
    assert report.duplicate_groups
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_nodes.py -v`
Expected: FAIL because node functions are not implemented yet.

**Step 3: Write minimal implementation**

Implement each node as a pure function or small callable that reads from and returns partial workflow state. Keep the reflection step deterministic and rule-based for the MVP.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_nodes.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/nodes tests/unit/test_nodes.py
git commit -m "feat: add workflow nodes"
```

### Task 6: Build the LangGraph main graph and case-generation subgraph

**Files:**
- Create: `app/graphs/__init__.py`
- Create: `app/graphs/case_generation.py`
- Create: `app/graphs/main_workflow.py`
- Test: `tests/integration/test_workflow.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from app.graphs.main_workflow import build_workflow


def test_workflow_returns_test_cases(fake_llm_client):
    workflow = build_workflow(fake_llm_client)
    result = workflow.invoke({"file_path": str(Path("tests/fixtures/sample_prd.md"))})
    assert result["test_cases"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_workflow.py -v`
Expected: FAIL because the graph does not exist and node wiring is missing.

**Step 3: Write minimal implementation**

Create the case-generation subgraph and main graph using `StateGraph`, wire node transitions in sequence, and ensure the graph returns a complete `GlobalState` payload.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/graphs tests/integration/test_workflow.py
git commit -m "feat: add langgraph workflow"
```

### Task 7: Add run repository and artifact persistence

**Files:**
- Create: `app/repositories/__init__.py`
- Create: `app/repositories/run_repository.py`
- Create: `app/utils/__init__.py`
- Create: `app/utils/filesystem.py`
- Test: `tests/unit/test_run_repository.py`

**Step 1: Write the failing test**

```python
from app.repositories.run_repository import FileRunRepository


def test_file_run_repository_persists_run(tmp_path):
    repo = FileRunRepository(tmp_path)
    repo.save("run-1", {"status": "succeeded"})
    assert repo.load("run-1")["status"] == "succeeded"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_run_repository.py -v`
Expected: FAIL because the repository layer does not exist.

**Step 3: Write minimal implementation**

Add a file-backed repository that saves intermediate and final workflow artifacts under `output/runs/<run_id>/`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_run_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/repositories app/utils tests/unit/test_run_repository.py
git commit -m "feat: add run artifact persistence"
```

### Task 8: Expose workflow execution through FastAPI routes

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Create: `app/services/__init__.py`
- Create: `app/services/workflow_service.py`
- Test: `tests/integration/test_api.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_create_run_returns_generated_cases(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": "tests/fixtures/sample_prd.md"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["test_cases"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_api.py -v`
Expected: FAIL because the route and workflow service are not implemented.

**Step 3: Write minimal implementation**

Create route handlers for health checks, run creation, and run lookup. Add a workflow service that wires settings, repository, client, and graph construction.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api app/main.py app/services tests/integration/test_api.py
git commit -m "feat: expose workflow via api"
```

### Task 9: Add documentation and environment setup guidance

**Files:**
- Modify: `README.md`
- Create: `.env.example`

**Step 1: Write the failing test**

There is no automated test for this documentation task. Instead, verify setup instructions by following them in a clean shell.

**Step 2: Run verification to confirm the gap**

Run: `test -f .env.example && echo exists`
Expected: no output before implementation because the file does not exist.

**Step 3: Write minimal implementation**

Document installation, environment variables, API usage, and example curl commands. Add `.env.example` with placeholders for the LLM client configuration.

**Step 4: Run verification to verify it passes**

Run: `test -f .env.example && echo exists`
Expected: `exists`

**Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs: add setup and usage instructions"
```

### Task 10: Run full verification

**Files:**
- Modify: `tests/conftest.py`
- Modify: any files required to fix failing verification

**Step 1: Write the failing test**

If shared fixtures are missing, add them before full verification. A minimal example:

```python
import pytest


@pytest.fixture
def fake_llm_client():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest -q`
Expected: one or more failures until all fixtures and integrations are wired correctly.

**Step 3: Write minimal implementation**

Add shared fixtures and fix any remaining gaps in workflow wiring, serialization, or API behavior.

**Step 4: Run test to verify it passes**

Run: `pytest -q`
Expected: PASS

**Step 5: Commit**

```bash
git add app tests
git commit -m "test: finalize mvp verification"
```
