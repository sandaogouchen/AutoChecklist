from __future__ import annotations

import asyncio

from app.config.settings import CocoSettings
from app.services.coco_client import CocoClient


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
