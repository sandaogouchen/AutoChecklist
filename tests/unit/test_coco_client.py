from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx

from app.config.settings import CocoSettings
from app.domain.mr_models import CodeConsistencyResult
from app.services.coco_client import CocoClient, CocoTaskError


def test_coco_settings_defaults_match_openapi_contract() -> None:
    settings = CocoSettings(_env_file=None)

    assert settings.coco_api_base_url == "https://codebase-api.byted.org/v2"
    assert settings.coco_agent_name == "sandbox"


def test_send_task_uses_supported_agent_and_omits_repo_id(monkeypatch) -> None:
    client = CocoClient(
        CocoSettings(
            _env_file=None,
            coco_jwt_token="token",
            coco_agent_name="autochecklist",
        )
    )
    captured: dict[str, object] = {}

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        captured["action"] = action
        captured["payload"] = payload
        return {"Task": {"Id": "task-123"}}

    monkeypatch.setattr(client, "_post", _fake_post)
    monkeypatch.setattr(
        client,
        "_resolve_repo_id",
        lambda mr_url, git_url: "",
        raising=False,
    )

    task_id = asyncio.run(
        client.send_task(
            prompt="review this MR",
            mr_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/merge_requests/2142",
            git_url="https://code.byted.org/ad/ttam_brand_mono.git",
        )
    )

    assert task_id == "task-123"
    assert captured["action"] == "SendCopilotTaskMessage"
    assert captured["payload"] == {
        "AgentName": "sandbox",
        "Message": {
            "Id": "",
            "Role": "user",
            "Parts": [{"Text": {"Text": "review this MR"}}],
        },
    }


def test_send_task_preserves_explicit_supported_agent(monkeypatch) -> None:
    client = CocoClient(CocoSettings(_env_file=None, coco_jwt_token="token"))
    captured: dict[str, object] = {}

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        captured["action"] = action
        captured["payload"] = payload
        return {"Task": {"Id": "task-456"}}

    monkeypatch.setattr(client, "_post", _fake_post)

    task_id = asyncio.run(
        client.send_task(
            prompt="review this MR",
            agent_name="copilot",
        )
    )

    assert task_id == "task-456"
    assert captured["payload"] == {
        "AgentName": "copilot",
        "Message": {
            "Id": "",
            "Role": "user",
            "Parts": [{"Text": {"Text": "review this MR"}}],
        },
    }


def test_send_task_includes_resolved_repo_id_for_internal_repo(monkeypatch) -> None:
    client = CocoClient(CocoSettings(_env_file=None, coco_jwt_token="token"))
    captured: dict[str, object] = {}

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        captured["action"] = action
        captured["payload"] = payload
        return {"Task": {"Id": "task-789"}}

    monkeypatch.setattr(client, "_post", _fake_post)
    monkeypatch.setattr(
        client,
        "_resolve_repo_id",
        lambda mr_url, git_url: "436797",
        raising=False,
    )

    task_id = asyncio.run(
        client.send_task(
            prompt="review this MR",
            mr_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/merge_requests/2142",
            git_url="https://code.byted.org/ad/ttam_brand_mono.git",
        )
    )

    assert task_id == "task-789"
    assert captured["payload"] == {
        "AgentName": "sandbox",
        "RepoId": "436797",
        "Message": {
            "Id": "",
            "Role": "user",
            "Parts": [{"Text": {"Text": "review this MR"}}],
        },
    }


def test_send_task_includes_configured_model_name(monkeypatch) -> None:
    client = CocoClient(
        CocoSettings(
            _env_file=None,
            coco_jwt_token="token",
            coco_model_name="kimi-k2-250711",
        )
    )
    captured: dict[str, object] = {}

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        captured["action"] = action
        captured["payload"] = payload
        return {"Task": {"Id": "task-model"}}

    monkeypatch.setattr(client, "_post", _fake_post)
    monkeypatch.setattr(
        client,
        "_resolve_repo_id",
        lambda mr_url, git_url: "",
        raising=False,
    )

    task_id = asyncio.run(client.send_task(prompt="review this MR"))

    assert task_id == "task-model"
    assert captured["payload"] == {
        "AgentName": "sandbox",
        "ModelName": "kimi-k2-250711",
        "Message": {
            "Id": "",
            "Role": "user",
            "Parts": [{"Text": {"Text": "review this MR"}}],
        },
    }


def test_poll_task_returns_completed_task(monkeypatch) -> None:
    client = CocoClient(CocoSettings(_env_file=None, coco_jwt_token="token"))

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        assert action == "GetCopilotTask"
        assert payload == {"TaskId": "task-123"}
        return {"Task": {"Id": "task-123", "Status": "completed"}}

    async def _fake_collect(task_id: str, timeout: int | None = None) -> list[dict[str, object]]:
        assert task_id == "task-123"
        return []

    monkeypatch.setattr(client, "_post", _fake_post)
    monkeypatch.setattr(client, "_collect_task_messages_via_sse", _fake_collect)

    task = asyncio.run(client.poll_task("task-123", timeout=5))

    assert task == {"Id": "task-123", "Status": "completed"}


def test_poll_task_attaches_messages_from_sse_when_completed(monkeypatch) -> None:
    client = CocoClient(CocoSettings(_env_file=None, coco_jwt_token="token"))

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        assert action == "GetCopilotTask"
        assert payload == {"TaskId": "task-123"}
        return {"Task": {"Id": "task-123", "Status": "completed"}}

    async def _fake_collect(task_id: str, timeout: int | None = None) -> list[dict[str, object]]:
        assert task_id == "task-123"
        assert timeout is not None
        return [
            {
                "Role": "agent",
                "Parts": [{"Text": {"Text": "{\"mr_summary\":\"ok\"}"}}],
            }
        ]

    monkeypatch.setattr(client, "_post", _fake_post)
    monkeypatch.setattr(client, "_collect_task_messages_via_sse", _fake_collect)

    task = asyncio.run(client.poll_task("task-123", timeout=5))

    assert task["Messages"][0]["Role"] == "agent"
    assert task["Messages"][0]["Parts"][0]["Text"]["Text"] == "{\"mr_summary\":\"ok\"}"


def test_get_assistant_text_accepts_agent_role() -> None:
    task = {
        "Messages": [
            {
                "Role": "agent",
                "Parts": [{"Text": {"Text": "{\"mr_summary\":\"ok\"}"}}],
            }
        ]
    }

    assert CocoClient._get_assistant_text(task) == "{\"mr_summary\":\"ok\"}"


def test_run_validation_task_uses_provided_timeout(monkeypatch) -> None:
    client = CocoClient(CocoSettings(_env_file=None, coco_jwt_token="token"))
    captured: dict[str, object] = {}

    async def _fake_send_task(prompt: str, mr_url: str = "", git_url: str = "", agent_name=None) -> str:
        del prompt, mr_url, git_url, agent_name
        return "task-validate"

    async def _fake_poll_task(task_id: str, timeout: int | None = None) -> dict[str, object]:
        captured["task_id"] = task_id
        captured["timeout"] = timeout
        return {"Id": task_id, "Status": "completed"}

    async def _fake_parse_validation_result(checkpoint, raw_text: str) -> CodeConsistencyResult:
        del checkpoint, raw_text
        return CodeConsistencyResult(status="confirmed", verified_by="coco")

    monkeypatch.setattr(client, "send_task", _fake_send_task)
    monkeypatch.setattr(client, "poll_task", _fake_poll_task)
    monkeypatch.setattr(client, "_parse_validation_result", _fake_parse_validation_result)
    monkeypatch.setattr(client, "_get_assistant_text", lambda task: "{}")

    result, _artifacts = asyncio.run(
        client.run_validation_task(
            checkpoint=SimpleNamespace(
                title="检查点",
                description="desc",
                objective="obj",
                preconditions=[],
            ),
            mr_context={"mr_url": "https://example.com/mr/1", "git_url": "https://example.com/repo.git"},
            timeout_s=2000,
        )
    )

    assert captured == {"task_id": "task-validate", "timeout": 2000}
    assert result.status == "confirmed"


def test_poll_task_raises_explicit_error_for_persistent_not_found(monkeypatch) -> None:
    client = CocoClient(
        CocoSettings(
            _env_file=None,
            coco_jwt_token="token",
            coco_poll_interval_start=0,
            coco_poll_interval_max=0,
        )
    )

    request = httpx.Request(
        "POST",
        "https://codebase-api.byted.org/v2/?Action=GetCopilotTask",
    )
    response = httpx.Response(
        404,
        request=request,
        content=json.dumps(
            {
                "ResponseMetadata": {
                    "Error": {
                        "Code": "NotFound.Task",
                        "Message": "resource Task is not found",
                    }
                }
            }
        ).encode(),
    )

    async def _fake_post(action: str, payload: dict[str, object]) -> dict[str, object]:
        raise httpx.HTTPStatusError("404 Not Found", request=request, response=response)

    monkeypatch.setattr(client, "_post", _fake_post)
    monotonic_values = iter([0.0, 16.0, 16.0])
    monkeypatch.setattr(
        "app.services.coco_client.time",
        SimpleNamespace(monotonic=lambda: next(monotonic_values)),
    )

    try:
        asyncio.run(client.poll_task("task-404", timeout=30))
    except CocoTaskError as exc:
        assert exc.task_id == "task-404"
        assert exc.status == "not_found"
        assert "NotFound.Task" in str(exc)
    else:
        raise AssertionError("expected CocoTaskError for persistent NotFound.Task")
