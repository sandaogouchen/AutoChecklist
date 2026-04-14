# AutoChecklist

AutoChecklist is a FastAPI service that reads a local Markdown PRD, runs a LangGraph workflow, calls an OpenAI-compatible LLM, and returns structured test cases in JSON and Markdown.

## Requirements

- Python 3.11+

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
```

Set the LLM environment variables in `.env`:

- `OUTPUT_DIR`
- `TIMEZONE`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_USE_COCO_AS_LLM`
- `LLM_USE_MIRA_AS_LLM`
- `LLM_TIMEOUT_SECONDS`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`

If you want to call Mira as the primary LLM provider, set:

- `LLM_USE_MIRA_AS_LLM=true`
- `LLM_MODEL=<mira model name>`
- `LLM_TIMEOUT_SECONDS=<request timeout seconds>`
- `TIMEZONE=<IANA timezone, for example Asia/Shanghai>`
- `MIRA_API_BASE_URL=<your mira base url>`
- `MIRA_JWT_TOKEN=<mira_session value>` or `MIRA_COOKIE=<full browser cookie>`
- `MIRA_CLIENT_VERSION=<client tag for diagnostics>`

In Mira mode, `LLM_MODEL` is still the effective model selector. `MIRA_JWT_TOKEN` is sent as the `mira_session` cookie value, not as a `jwt-token` header. `MIRA_COOKIE` can be used when you want to replay the full browser `Cookie` header.

When reusing browser-authenticated Mira Web traffic such as `https://mira.bytedance.com`, prefer:

- `MIRA_API_BASE_URL=https://mira.bytedance.com`
- `MIRA_COOKIE=<full Cookie header copied from browser request>`
- `MIRA_CLIENT_VERSION=0.61.0_extension`

If you want MR analysis and checkpoint code-consistency checks to use Mira instead of Coco Task1/Task2, also set:

- `MIRA_USE_FOR_CODE_ANALYSIS=true`

If you want to call Coco OpenAPI as the primary LLM provider, set:

- `LLM_USE_COCO_AS_LLM=true`
- `COCO_API_BASE_URL=https://codebase-api.byted.org/v2`
- `COCO_JWT_TOKEN=<your token>`
- `COCO_AGENT_NAME=sandbox` or `copilot`

In Coco mode, `LLM_MODEL` maps to Coco `ModelName`, and request routing uses `COCO_API_BASE_URL` instead of `LLM_BASE_URL`. Knowledge retrieval remains disabled in this mode because Coco OpenAPI does not expose embeddings.

When `MIRA_USE_FOR_CODE_ANALYSIS=true`, request-level `use_coco=true` still enables remote code analysis, but the backend is switched from Coco to Mira while preserving the existing workflow output shape and artifact layout.

## Run The API

```bash
.venv/bin/uvicorn app.main:app --reload
```

## API Endpoints

- `GET /healthz`
- `POST /api/v1/case-generation/runs`
- `GET /api/v1/case-generation/runs/{run_id}`

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/case-generation/runs \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/absolute/path/to/prd.md",
    "language": "zh-CN",
    "model_config": {
      "temperature": 0.2,
      "max_tokens": 1600
    }
  }'
```

Artifacts are written to `output/runs/<run_id>/` by default.

## Run Tests

```bash
.venv/bin/pytest -q
```
