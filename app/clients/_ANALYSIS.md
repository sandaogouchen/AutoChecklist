# app/clients/ Directory Analysis

## §4.1 Directory Overview

The `app/clients/` directory contains a single module, `llm.py`, which provides the foundational LLM interaction layer for the entire AutoChecklist system. This module is the **sole interface** between the application and external LLM APIs (OpenAI-compatible endpoints).

Every LLM-calling node in the workflow graphs (§6) -- `context_research`, `checkpoint_generator`, `checkpoint_outline_planner`, `draft_writer`, and `mr_analyzer` -- depends on the `LLMClient` class defined here. The reliability, retry behavior, and output parsing quality of this module directly determine the robustness of the entire pipeline.

**Technology**: OpenAI Python SDK (`openai` package), Pydantic v2 for structured output validation, standard library `json`/`re` for response parsing.

---

## §4.2 File Analysis

### §4.2.1 llm.py

**Type**: Type A -- Core Infrastructure  
**Criticality**: **CRITICAL**  
**Lines**: ~500  
**Primary Exports**: `LLMClient`, `OpenAICompatibleLLMClient`, `LLMClientConfig`

#### Architecture Overview

The module provides three main abstractions:

1. **`LLMClientConfig`** (dataclass) -- Configuration container for all LLM connection, retry, and fallback parameters.
2. **`LLMClient`** -- The core client class with three public methods: `chat()`, `parse_json_response()`, `generate_structured()`.
3. **`OpenAICompatibleLLMClient`** -- A convenience subclass that constructs `LLMClient` from a `LLMClientConfig` instance.

#### Retry Mechanism with Exponential Backoff + Jitter

The retry system is implemented in `_chat_with_retry()` and follows a well-designed pattern:

**Retryable conditions** (defined in `_is_retryable()`):
- `APIConnectionError` -- network connectivity failure
- `APITimeoutError` -- request timeout
- `APIStatusError` with status code in `{429, 500, 502, 503}`

**Non-retryable conditions** (immediate raise):
- HTTP 400 (bad request), 401 (auth failure), 403 (permission denied)
- `ValidationError` (Pydantic schema mismatch)
- Any other non-API exception

**Backoff formula**:
```python
delay = min(retry_base_delay * (2 ** attempt), retry_max_delay)
jittered_delay = random.uniform(0, delay)  # Full jitter
```

This is the standard "full jitter" strategy recommended by AWS and other distributed systems best practices. The `random.uniform(0, delay)` spreads retry attempts uniformly across the backoff window, preventing thundering herd effects when multiple pipeline nodes retry simultaneously.

**Configuration defaults**:
- `max_retries`: 3 (total 4 attempts)
- `retry_base_delay`: 1.0 second
- `retry_max_delay`: 60.0 seconds
- Effective delays: attempt 1 -> [0, 1s], attempt 2 -> [0, 2s], attempt 3 -> [0, 4s]

**SDK retry disabled**: The OpenAI SDK's built-in retry is explicitly disabled (`max_retries=0`) in favor of the application-level retry logic. This gives full control over retry behavior and logging.

#### Model Fallback / Degradation Support

When the primary model exhausts all retries, the client can automatically fall back to a secondary model:

```
Primary model (with retries) → [exhausted] → Fallback model (with retries)
```

**Fallback configuration** (in `LLMClientConfig`):
- `fallback_model`: Model name for the backup LLM
- `fallback_base_url`: Optional separate API endpoint
- `fallback_api_key`: Optional separate API key

**Fallback behavior**:
1. A separate `OpenAI` client instance is constructed for the fallback model
2. Fallback gets the same retry strategy as the primary
3. Structured logging tracks both primary and fallback errors
4. If fallback also fails, the fallback's last exception is raised

**Use case**: This enables running a high-quality model (e.g., GPT-4o) as primary with a faster/cheaper model (e.g., GPT-3.5-turbo) as fallback, providing graceful degradation under primary model outages.

#### Core Method: `chat()`

The `chat()` method is the fundamental LLM interaction:
1. Constructs a `[system, user]` message pair
2. Calls `_chat_with_retry()` with the primary client
3. On failure, attempts fallback if configured
4. Returns raw text string

Supports per-call `temperature` and `max_tokens` overrides.

#### Core Method: `parse_json_response()`

A static method that extracts JSON from LLM output text using a multi-strategy approach:

1. **Direct parse**: Try `json.loads()` on the entire stripped text
2. **Fenced code block extraction**: Regex for `` ```json ... ``` `` patterns
3. **Stack-based scanner**: Character-by-character scanning to find the first balanced `{}` or `[]` structure, correctly handling string escaping

The stack-based scanner is particularly robust -- it tracks string boundaries, escape characters, and nesting depth to find valid JSON even when surrounded by explanation text. This handles common LLM behaviors like:
- Wrapping JSON in markdown code blocks
- Preceding JSON with explanation text
- Following JSON with additional commentary

#### Core Method: `generate_structured()`

Combines `chat()` + `parse_json_response()` + Pydantic `model_validate()` into a single call that returns a validated Pydantic model instance:

1. **Schema injection**: Calls `_build_schema_hint(response_model)` to generate a JSON Schema constraint string (truncated to 3000 chars) that is appended to the system prompt. This guides the LLM to produce schema-compliant output.

2. **JSON mode**: Passes `response_format={"type": "json_object"}` to the API call, requesting structured JSON output from the LLM.

3. **List-to-dict auto-wrapping**: If the LLM returns a top-level JSON array but the response model expects a dict with a single list field, automatically wraps the array. This handles a common LLM behavior where the model outputs a bare array instead of wrapping it in the expected object structure.

4. **Diagnostic logging**: If any list field in the validated result is empty, logs a warning with the first 500 characters of the LLM's raw response. This helps debug cases where the LLM produces structurally valid but semantically empty output.

5. **Error messages include raw output**: All error messages (JSON parse failure, Pydantic validation failure) include the first 2000 characters of the LLM's raw response, enabling diagnosis from workflow logs without requiring reproduction.

#### Helper: `_build_schema_hint()`

Generates a JSON Schema string from a Pydantic model and formats it as a prompt injection:
- Extracts schema via `response_model.model_json_schema()`
- Serializes to JSON string
- Truncates to 3000 characters if too large
- Wraps in a `--- JSON Schema Constraint ---` block with explicit instructions
- Returns empty string on any exception (graceful degradation)

#### `OpenAICompatibleLLMClient` Subclass

A thin subclass that accepts `LLMClientConfig` and passes all parameters to `LLMClient.__init__()`. Also stores the original `config` for downstream access.

---

## §4.3 Key Findings

1. **Single point of LLM interaction**: All LLM calls in the system route through this module. Any change to retry logic, timeout handling, or error classification affects every node in the pipeline. This is both a strength (centralized control) and a risk (single point of failure in the abstraction).

2. **Robust JSON extraction**: The three-strategy JSON parsing approach (`parse_json_response`) handles the majority of LLM output formatting variations. The stack-based scanner is particularly valuable for production reliability, as it handles edge cases that regex-only approaches miss.

3. **Full jitter backoff is best-practice**: The `random.uniform(0, delay)` jitter strategy is the optimal choice for distributed retry scenarios, preventing synchronized retry storms.

4. **Synchronous-only design**: All methods are synchronous, using the synchronous `OpenAI` client. This means LLM calls block the calling thread. In the context of the FastAPI application (§3), this works because the sync route handler runs in FastAPI's thread pool, but it prevents true async pipeline execution.

5. **No token counting or cost tracking**: The module does not track token usage, estimated costs, or rate limit headers from API responses. For production deployments with budget constraints, this information would be valuable.

6. **No response caching**: Identical prompts always result in fresh API calls. For development/testing scenarios, a response cache could significantly reduce costs and latency.

7. **Schema hint truncation**: The 3000-character limit on schema hints may be insufficient for complex response models with many nested fields, potentially omitting critical structural constraints.

8. **Thread safety**: The `OpenAI` client instances are created once and reused across calls. The OpenAI SDK's synchronous client uses `httpx.Client` which is thread-safe, so concurrent calls from different workflow nodes (if parallelism were added) should be safe.

9. **Fallback retry duplication**: The retry-then-fallback logic is duplicated between `chat()` and `generate_structured()`. The `generate_structured()` method reimplements the fallback pattern rather than delegating to `chat()`, because it needs to pass `response_format={"type": "json_object"}` which `chat()` does not support.

---

## §4.4 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `LLMClient` injected into | `app/graphs/main_workflow.py` (§6) | Passed to `build_workflow()` |
| `LLMClient` used by | `app/nodes/context_research.py` | `build_context_research_node(llm_client)` |
| `LLMClient` used by | `app/nodes/checkpoint_generator.py` | `build_checkpoint_generator_node(llm_client)` |
| `LLMClient` used by | `app/services/checkpoint_outline_planner.py` | `build_checkpoint_outline_planner_node(llm_client)` |
| `LLMClient` used by | `app/nodes/draft_writer.py` | `DraftWriterNode(llm_client)` |
| `LLMClient` used by | `app/nodes/mr_analyzer.py` | `build_mr_analyzer_node(llm_client)` |
| `LLMClientConfig` from | `app/config/settings.py` | Configuration source |
| `OpenAICompatibleLLMClient` used by | `app/services/workflow_service.py` | Service layer construction |
| OpenAI SDK | External dependency | `openai` package |
| GraphRAG LLM callback | `app/knowledge/graphrag_engine.py` (§13) | Separate LLM path (httpx-based, not via LLMClient) |