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

`LLM_BASE_URL` can be either a provider base URL such as `https://api.openai.com/v1` or a full endpoint such as `http://localhost:8317/v1/chat/completions/`.

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

Success responses return a lightweight run summary in the `result` wrapper:

```json
{
  "run_id": "123",
  "status": "succeeded",
  "result": {
    "run_id": "123",
    "status": "succeeded",
    "test_case_count": 1,
    "warning_count": 0,
    "artifacts": {
      "request": "output/runs/123/request.json",
      "parsed_document": "output/runs/123/parsed_document.json",
      "research_output": "output/runs/123/research_output.json",
      "test_cases": "output/runs/123/test_cases.json",
      "test_cases_markdown": "output/runs/123/test_cases.md",
      "quality_report": "output/runs/123/quality_report.json",
      "run_result": "output/runs/123/run_result.json"
    },
    "outputs": [
      {
        "key": "test_cases_markdown",
        "path": "output/runs/123/test_cases.md",
        "kind": "file",
        "format": "markdown"
      },
      {
        "key": "platform_delivery",
        "path": "output/runs/123-platform.json",
        "kind": "platform",
        "format": "json"
      }
    ]
  }
}
```

Failed runs return a compact error payload:

```json
{
  "run_id": "123",
  "status": "failed",
  "error": {
    "code": "ValidationError",
    "message": "value must not be empty",
    "detail": {}
  }
}
```

Artifacts are written only for successful runs to `output/runs/<run_id>/` by default.

Contract notes:

- Failed runs do not create an output directory.
- `GET /api/v1/case-generation/runs/{run_id}` is guaranteed across process restarts only for successful runs, because only successful summaries are persisted to disk.
- The platform delivery step currently writes a local JSON adapter output. A real platform publisher can replace it without changing the output subgraph contract.

## Run Tests

```bash
.venv/bin/pytest -q
```
