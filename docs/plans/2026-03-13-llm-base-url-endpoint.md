# LLM Base URL Endpoint Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow `LLM_BASE_URL` to point either to a legacy OpenAI-compatible base URL or directly to a full `chat/completions` endpoint.

**Architecture:** Keep URL compatibility logic inside `OpenAICompatibleLLMClient` so callers continue passing a single `base_url` setting. Normalize the configured URL once during client setup: preserve explicit `chat/completions` endpoints as-is, otherwise append `/chat/completions` for legacy base URLs.

**Tech Stack:** Python 3.11, `httpx`, `pydantic`, `pytest`

---

### Task 1: Lock the URL behavior with tests

**Files:**
- Modify: `tests/unit/test_llm_client.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: Write the failing test**

Add one test proving `https://example.com/v1` still resolves to `https://example.com/v1/chat/completions`, and one test proving `http://localhost:8317/v1/chat/completions/` is not extended again.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_client.py -q`
Expected: FAIL because the client currently always posts to `"/chat/completions"`.

### Task 2: Implement endpoint normalization in the client

**Files:**
- Modify: `app/clients/llm.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: Write minimal implementation**

Add a small helper that trims trailing slashes, detects an existing `chat/completions` suffix, and otherwise appends `/chat/completions`. Use the normalized URL when creating the `httpx` client and post to the current endpoint without adding another suffix.

**Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_client.py -q`
Expected: PASS

### Task 3: Verify surrounding behavior

**Files:**
- Modify: `README.md` (only if setup docs need clarification)
- Test: `tests/unit/test_llm_client.py`

**Step 1: Confirm docs/tests**

If the README does not already clarify accepted `LLM_BASE_URL` formats, add one short note with both supported examples.

**Step 2: Run final verification**

Run: `.venv/bin/pytest tests/unit/test_llm_client.py tests/unit/test_settings.py -q`
Expected: PASS
