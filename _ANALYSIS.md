# Root Directory Analysis

> Auto-generated analysis for the root directory of AutoChecklist

## §1.1 Directory Overview

| Property | Value |
|----------|-------|
| Path | `/` |
| Total Files | 4 (`README.md`, `.env.example`, `pyproject.toml`, `prd.md`) |
| Main Purpose | Project root containing documentation, build configuration, environment variable templates, and product requirements specification for the AutoChecklist service |

The root directory establishes the project identity, dependency surface, environment contract, and product vision. It contains no executable source code; all application logic resides under the `app/` package.

---

## §1.2 File Analysis

### §1.2.1 README.md

**Type**: B -- Documentation

**Audience**: Developers setting up, running, or contributing to the AutoChecklist service.

**Key Sections**:

| Section | Content Summary |
|---------|----------------|
| Title / Introduction | One-sentence description: FastAPI service that reads a Markdown PRD, runs a LangGraph workflow, calls an OpenAI-compatible LLM, and returns structured test cases in JSON and Markdown. |
| Requirements | Python 3.11+ (no upper bound specified). |
| Setup | `venv` creation, editable install with dev extras, `.env` copy. |
| Environment Variables | Lists six LLM-related variables: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`. |
| Run The API | Single `uvicorn` command with `--reload`. |
| API Endpoints | Three endpoints: health check (`GET /healthz`), create run (`POST /api/v1/case-generation/runs`), get run (`GET /api/v1/case-generation/runs/{run_id}`). |
| Example Request | `curl` example showing `file_path`, `language`, and `model_config` fields. |
| Run Tests | `pytest -q` via the venv. |

**Accuracy Notes**:
- The README lists only the original three API endpoints. It does not document the newer knowledge-management routes (`/api/v1/knowledge/...`) or the project-context routes registered in `main.py`. These routes are registered via `knowledge_routes` and `project_routes` routers and represent a documentation gap.
- The README lists only six LLM environment variables; the `.env.example` file defines significantly more (retry, fallback, knowledge retrieval). The README should be updated for completeness.
- The `output/runs/<run_id>/` artifact path mentioned in the README aligns with the `output_dir` default in `config/settings.py`.

---

### §1.2.2 pyproject.toml

**Type**: D -- Configuration (build / dependency manifest)

**Build System**: Implicit (no `[build-system]` table), relies on PEP 621 project metadata.

**Project Metadata**:

| Field | Value |
|-------|-------|
| `name` | `auto-checklist` |
| `version` | `0.1.0` |
| `description` | "Automated test checklist generation from PRD documents" |
| `readme` | `README.md` |
| `requires-python` | `>=3.11` |

**Runtime Dependencies** (12 packages):

| Package | Version Constraint | Purpose |
|---------|--------------------|----------|
| `fastapi` | `>=0.115.12` | Web framework / API layer |
| `httpx` | `>=0.28.1` | Async HTTP client (used by OpenAI SDK and custom clients) |
| `langgraph` | `>=0.3.34` | LangGraph workflow orchestration engine |
| `lightrag-hku` | `>=1.1.0` | LightRAG / GraphRAG knowledge retrieval engine |
| `openai` | `>=1.68.2` | OpenAI-compatible LLM client |
| `pydantic` | `>=2.11.1` | Data validation / domain models |
| `pydantic-settings` | `>=2.11.0` | Environment-based settings management |
| `python-dotenv` | `>=1.1.0` | `.env` file loading |
| `python-multipart` | `>=0.0.20` | Multipart form data support for FastAPI |
| `pyyaml` | `>=6.0.1` | YAML parsing (likely for templates / configuration files) |
| `uvicorn` | `>=0.34.2` | ASGI server |

**Dev Dependencies** (`[dependency-groups] dev`):

| Package | Version Constraint | Purpose |
|---------|--------------------|----------|
| `pytest` | `>=8.3.5` | Test runner |
| `pytest-asyncio` | `>=0.26.0` | Async test support |

**Compatibility Notes**:
- All version constraints use `>=` (floor only, no ceiling). This maximises compatibility but may introduce breaking changes from future major releases. Pinning upper bounds or using a lockfile is recommended for production stability.
- `requires-python = ">=3.11"` matches the README.
- No `[build-system]` table is declared. Modern tooling (pip >= 21.3) defaults to `setuptools`, but explicitly declaring it is best practice.
- No entry-point scripts are defined; the application is launched via `uvicorn app.main:app`.

---

### §1.2.3 .env.example

**Type**: D -- Configuration (environment variable template)

**Purpose**: Serves as the canonical contract for all environment variables consumed by the application. Developers copy this to `.env` and fill in secrets.

**Variable Inventory**:

| Variable | Default Value | Required | Purpose | Security Sensitivity |
|----------|---------------|----------|---------|---------------------|
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Yes | Base URL for the OpenAI-compatible API | Low |
| `LLM_MODEL` | `gpt-4.1-mini` | Yes | Model identifier for the primary LLM | Low |
| `LLM_TIMEOUT_SECONDS` | `6000` | No | Request timeout in seconds | Low |
| `LLM_TEMPERATURE` | `0.2` | No | Sampling temperature | Low |
| `LLM_MAX_TOKENS` | `1600` | No | Maximum tokens per response | Low |
| `LLM_API_KEY` | *(not shown, implied)* | **Yes** | API key for the primary LLM | **HIGH -- secret** |
| **Retry & Fallback** | | | | |
| `LLM_MAX_RETRIES` | `3` | No | Maximum retry attempts (0 disables) | Low |
| `LLM_RETRY_BASE_DELAY` | `1.0` | No | Initial exponential back-off delay (seconds) | Low |
| `LLM_RETRY_MAX_DELAY` | `60.0` | No | Maximum back-off cap (seconds) | Low |
| `LLM_FALLBACK_MODEL` | *(empty)* | No | Fallback model name; empty disables degradation | Low |
| `LLM_FALLBACK_BASE_URL` | *(empty)* | No | Fallback API base URL; empty reuses primary | Low |
| `LLM_FALLBACK_API_KEY` | *(empty)* | No | Fallback API key; empty reuses primary | **HIGH -- secret** |
| **Knowledge Retrieval** | | | | |
| `ENABLE_KNOWLEDGE_RETRIEVAL` | `false` | No | Feature flag for GraphRAG / LightRAG | Low |
| `KNOWLEDGE_WORKING_DIR` | `./knowledge_db` | No | LightRAG index data directory | Low |
| `KNOWLEDGE_DOCS_DIR` | `./knowledge_docs` | No | Source knowledge Markdown directory | Low |
| `KNOWLEDGE_RETRIEVAL_MODE` | `hybrid` | No | Retrieval strategy: `naive`, `local`, `global`, `hybrid` | Low |
| `KNOWLEDGE_TOP_K` | `10` | No | Max results per retrieval query | Low |
| `KNOWLEDGE_EMBEDDING_MODEL` | *(empty)* | No | Embedding model; empty reuses `LLM_MODEL` | Low |
| `KNOWLEDGE_MAX_DOC_SIZE_KB` | `1024` | No | Per-document size cap in KB | Low |

**Notes**:
- `LLM_API_KEY` is referenced in the README but does not appear literally in `.env.example`. The Settings class maps it from the environment variable `LLM_API_KEY` to `llm_api_key`. Developers must add it manually.
- Three variables carry secret credentials (`LLM_API_KEY`, `LLM_FALLBACK_API_KEY`, and potentially `COCO_API_KEY` from `CocoSettings`). The `.env` file must be git-ignored.
- The `LLM_MAX_TOKENS` default in `.env.example` is `1600`, but `settings.py` declares a default of `50000`. The `.env.example` value will override the code default when copied. This discrepancy could confuse developers.
- Comments in the file are in Chinese, consistent with the project's primary development language context.

---

### §1.2.4 prd.md

**Type**: B -- Documentation (Product Requirements Document)

**Purpose**: Comprehensive product requirements specification that defines the architecture, features, and implementation plan for the AutoChecklist system.

**Document Structure**:

| Section | Content |
|---------|----------|
| 一、核心架构设计 (Core Architecture) | Four-layer architecture: Input Layer, Context Research Layer, Case Generation Layer, Reflection Optimization Layer. State management (GlobalState / CaseGenState). Workflow node design (InputParserNode, ContextResearchNode, CaseGenNode, ReflectionNode). |
| 二、核心功能模块 (Core Functional Modules) | Multi-modal document parsing, intelligent requirement understanding (test signal tagging with 7 signal types), test case generation (scenario planning, evidence mapping, draft writing, structure assembly), quality optimization (redundancy checks, semantic dedup, rule compliance), business adaptation (templates, multi-language, localization). |
| 三、技术实现要点 (Technical Implementation) | LangGraph workflow design, intelligent agent architecture (Lead-Worker pattern), data processing pipeline. |
| 四、开发实施内容 (Development Implementation) | Module development breakdown, workflow implementation, business integration, monitoring. |
| 五、关键优化特性 (Key Optimizations) | Documented optimization results: case reduction from 362 to 95 (internal redundancy), 95 to 82 (inter-case dedup), 82 to 57 (content weighting). Business template support. |

**Key Requirements & Acceptance Criteria (implicit)**:
- Four-layer pipeline must execute sequentially: parse -> research -> generate -> reflect.
- Seven test-signal categories must be identified: behavior, state change, condition, exception, UI feedback, constraint, ambiguous.
- Knowledge graph must support five entity types: functional theme, user scenario, requirement atom, global constraint, ambiguity point.
- Case generation sub-graph must contain four ordered nodes: scenario planner, evidence mapper, draft writer, structure assembler.
- Quality optimization must include: internal redundancy check, semantic deduplication, rule compliance validation, comprehensive quality assessment.
- Multi-language support with three adaptation modes: full translation, keyword preservation, hybrid.
- Template management with three-tier structure: base, business-line, project.

**Observations**:
- The PRD is written entirely in Chinese, reflecting the target user base.
- It is a living design document that also serves as a test input artifact (the README example shows passing a PRD file path to the API).
- Quantitative optimization metrics are cited but attributed to external sources (footnote markers `1` without actual footnotes).
- The scope described in the PRD is significantly broader than the current codebase implementation (e.g., Figma integration, internet search tools, code repository queries are mentioned but may not yet be implemented).

---

## §1.3 Key Findings

- **Documentation gap**: The README documents only the original 3 API endpoints. The knowledge-management routes and project-context routes added later are not mentioned, reducing onboarding accuracy.
- **LLM_MAX_TOKENS default mismatch**: `.env.example` sets `1600`, while `settings.py` defaults to `50000`. When a developer copies `.env.example` verbatim, they get 1600 -- which may be insufficient for the complex multi-step workflow. This discrepancy should be resolved.
- **Missing LLM_API_KEY in .env.example**: The most critical variable (`LLM_API_KEY`) is not listed in the template file, though it is referenced in the README and required by `settings.py`.
- **No build-system declaration**: `pyproject.toml` omits `[build-system]`, relying on implicit setuptools detection. Adding an explicit declaration improves reproducibility.
- **Unbounded dependency versions**: All runtime dependencies use `>=` floor-only constraints. A lockfile or upper-bound pins should be introduced before production deployment.
- **PRD scope vs. implementation**: The PRD describes capabilities (Figma parsing, internet search, code repository queries, Feishu document parsing) that may not yet be fully implemented. The PRD should be reconciled with actual implementation status.
- **Security-sensitive variables**: Three environment variables carry API secrets. The `.env` file must remain in `.gitignore` (not verified in this analysis scope).
- **Chinese-language documentation**: Both the PRD and `.env.example` comments are in Chinese, which may affect international contributor onboarding.

---

## §1.4 Cross-References

| Reference | Target |
|-----------|--------|
| `pyproject.toml` dependencies | See §2.2.3 for how `pydantic-settings` is used in `config/settings.py` |
| `.env.example` variables | See §2.2.3 for the `Settings` class field-by-field mapping |
| README API endpoints | See §2.2.1 for `main.py` route registration and additional routers |
| PRD architecture layers | See §2.3 for the actual `app/` subdirectory structure mapping to the four-layer design |
| `output/runs` artifact path | See §2.2.3 `Settings.output_dir` default value |
| `LLM_*` configuration | See §2.2.3 for all LLM-related Settings fields and their defaults |
| Knowledge retrieval feature | See §2.2.1 for GraphRAG engine lifecycle management in `_lifespan()` |