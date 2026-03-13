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

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`

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
