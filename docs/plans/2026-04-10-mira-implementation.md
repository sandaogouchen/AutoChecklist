# Mira Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Mira as the unified LLM backend, externalize prompt templates, and replace the current Coco-based MR analysis and checkpoint consistency checks with Mira while preserving existing workflow outputs and rollback safety.

**Architecture:** Keep the public `LLMClient` interface stable and move backend selection behind strategy-style dispatch. Add a standalone `MiraClient` plus `PromptLoader`, then switch MR-analysis internals from Coco task APIs to Mira session/message APIs without changing downstream state keys, artifact layout, or domain models. Retain backward compatibility so non-Mira paths continue to work unchanged.

**Tech Stack:** Python 3.11, Pydantic, httpx, LangGraph, pytest

---

### Task 1: Lock Config and Backend Selection

**Files:**
- Modify: `app/config/settings.py`
- Modify: `app/clients/llm.py`
- Modify: `tests/unit/test_llm_client.py`
- Modify: `tests/unit/test_workflow_service_coco.py`

**Step 1: Write the failing tests**

Add tests that assert:
- `Settings` exposes Mira-related fields.
- `WorkflowService._get_llm_client()` passes Mira config through.
- `OpenAICompatibleLLMClient` can select Mira backend without breaking existing OpenAI and Coco behavior.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_workflow_service_coco.py -q`

Expected: failures for missing Mira config / backend behavior.

**Step 3: Write minimal implementation**

Add Mira config fields and backend-selection plumbing while preserving existing signatures.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_workflow_service_coco.py -q`

Expected: PASS.

### Task 2: Add Mira Client and Prompt Loader

**Files:**
- Create: `app/clients/mira_client.py`
- Create: `app/services/prompt_loader.py`
- Create: `tests/unit/test_mira_client.py`
- Create: `tests/unit/test_prompt_loader.py`

**Step 1: Write the failing tests**

Add tests for:
- Mira session create/delete request shapes.
- SSE payload assembly into final assistant text.
- prompt file loading, caching, and missing-template errors.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mira_client.py tests/unit/test_prompt_loader.py -q`

Expected: FAIL because the new modules do not exist yet.

**Step 3: Write minimal implementation**

Implement:
- `MiraClientConfig`, `MiraMessageResponse`, `MiraFileInfo`, `MiraModelMetadata`
- session/file/model/message methods needed by this repo
- `PromptLoader` with repo-root `prompts/` support

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mira_client.py tests/unit/test_prompt_loader.py -q`

Expected: PASS.

### Task 3: Externalize Existing Prompt Templates

**Files:**
- Create: `prompts/...` for all current hardcoded prompts
- Modify: `app/nodes/context_research.py`
- Modify: `app/nodes/checkpoint_generator.py`
- Modify: `app/nodes/draft_writer.py`
- Modify: `app/nodes/mr_analyzer.py`
- Modify: `app/services/checkpoint_outline_planner.py`
- Modify: `app/services/semantic_path_normalizer.py`
- Modify: `app/services/coco_client.py` or successor prompt builder module
- Add/modify related tests under `tests/unit/`

**Step 1: Write the failing tests**

Add or extend tests so they assert prompt-dependent output still contains the same required guidance after loading from files.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_nodes.py tests/unit/test_checkpoint.py tests/unit/test_draft_writer.py tests/unit/test_checkpoint_outline_planner.py tests/unit/test_mr_analyzer.py -q`

Expected: FAIL where modules still rely on removed inline prompt constants.

**Step 3: Write minimal implementation**

Move prompt bodies to Markdown/text templates and load them with `PromptLoader`, keeping `.format()` placeholder names stable.

**Step 4: Run tests to verify they pass**

Run the same pytest command.

Expected: PASS.

### Task 4: Route Structured and Plain LLM Calls Through Mira

**Files:**
- Modify: `app/clients/llm.py`
- Modify: `app/services/workflow_service.py`
- Modify: `tests/unit/test_llm_client.py`
- Modify: `tests/unit/test_workflow_service_coco.py`

**Step 1: Write the failing tests**

Add tests that assert:
- Mira backend receives merged prompts and returns plain text.
- `generate_structured()` still injects schema hints and repairs invalid JSON in Mira mode.
- existing OpenAI and Coco-backed LLM tests remain green.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_workflow_service_coco.py -q`

Expected: FAIL for unimplemented Mira path.

**Step 3: Write minimal implementation**

Wire `LLMClient` to instantiate and use `MiraClient` when Mira is enabled, leaving other backends unchanged.

**Step 4: Run tests to verify they pass**

Run the same pytest command.

Expected: PASS.

### Task 5: Replace Coco Task 1/Task 2 with Mira Analysis Services

**Files:**
- Create: `app/services/mira_analysis_service.py`
- Modify: `app/nodes/mr_analyzer.py`
- Modify: `app/nodes/coco_consistency_validator.py`
- Modify: `app/domain/mr_models.py`
- Create/modify: `tests/unit/test_mr_analyzer.py`
- Create/modify: `tests/unit/test_coco_consistency_validator.py`

**Step 1: Write the failing tests**

Add tests that assert:
- MR analysis in Mira mode still returns `MRAnalysisResult`.
- checkpoint validation still returns `CodeConsistencyResult` and annotates tags/TODOs correctly.
- artifact files remain under `output/.../coco/` for compatibility unless the code intentionally renames them everywhere.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mr_analyzer.py tests/unit/test_coco_consistency_validator.py -q`

Expected: FAIL for missing Mira-backed analysis path.

**Step 3: Write minimal implementation**

Implement Mira-backed MR analysis and checkpoint validation services that:
- create/reuse Mira sessions
- send prompt messages
- parse structured results into existing domain models
- persist compatible artifacts

**Step 4: Run tests to verify they pass**

Run the same pytest command.

Expected: PASS.

### Task 6: Update Docs and Run Focused Regression

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: any touched tests if regressions appear

**Step 1: Write the failing tests**

Only if documentation/config tests exist; otherwise skip this step and validate via runtime checks.

**Step 2: Run focused regression**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_mr_analyzer.py tests/unit/test_coco_consistency_validator.py tests/unit/test_nodes.py tests/unit/test_checkpoint.py tests/unit/test_draft_writer.py tests/unit/test_checkpoint_outline_planner.py tests/unit/test_workflow_service_coco.py -q`

Expected: all targeted tests pass.

**Step 3: Run broader regression if affordable**

Run: `pytest -q`

Expected: all tests pass, or capture remaining unrelated failures explicitly.
