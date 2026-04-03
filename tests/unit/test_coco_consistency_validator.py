"""Unit tests for coco consistency validator node."""

from __future__ import annotations

import asyncio

from app.config.settings import CocoSettings
from app.domain.checkpoint_models import Checkpoint
from app.nodes import coco_consistency_validator as validator_module
from app.nodes.coco_consistency_validator import (
    _resolve_total_timeout_s,
    build_coco_consistency_validator_node,
)


def test_coco_consistency_validator_returns_empty_dict_without_coco_config() -> None:
    node = build_coco_consistency_validator_node()

    result = node(
        {
            "checkpoints": [Checkpoint(title="验证登录成功")],
            "frontend_mr_config": {"use_coco": False},
        }
    )

    assert result == {}
    assert isinstance(result, dict)


def test_coco_consistency_validator_runs_synchronously_with_coco(monkeypatch) -> None:
    async def _fake_validate_checkpoint_via_coco(
        checkpoint,
        mr_context,
        coco_settings,
        llm_client,
        artifact_context=None,
    ):
        del mr_context, coco_settings, llm_client, artifact_context
        return (
            validator_module.CodeConsistencyResult(
                status="confirmed",
                confidence=0.95,
                actual_implementation="代码与预期一致",
                verified_by="coco",
            ),
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_title": checkpoint.title,
            },
        )

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_coco",
        _fake_validate_checkpoint_via_coco,
    )

    node = build_coco_consistency_validator_node(
        coco_settings=CocoSettings(coco_jwt_token="dummy-token"),
    )
    checkpoint = Checkpoint(title="验证登录成功")

    result = node(
        {
            "checkpoints": [checkpoint],
            "frontend_mr_config": {
                "mr_url": "https://example.com/mr/123",
                "use_coco": True,
                "codebase": {"git_url": "https://example.com/repo.git"},
            },
        }
    )

    assert isinstance(result, dict)
    assert result["coco_validation_summary"] == {
        "total": 1,
        "confirmed": 1,
        "mismatch": 0,
        "unverified": 0,
    }
    assert result["checkpoints"][0].code_consistency["status"] == "confirmed"


def test_resolve_total_timeout_scales_with_checkpoint_count(monkeypatch) -> None:
    monkeypatch.setattr(validator_module, "_MAX_CONCURRENCY", 5)
    monkeypatch.setattr(validator_module, "_PER_CASE_TIMEOUT_S", 120)
    monkeypatch.setattr(validator_module, "_TOTAL_TIMEOUT_S", 600)

    assert _resolve_total_timeout_s(0) == 600
    assert _resolve_total_timeout_s(5) == 600
    assert _resolve_total_timeout_s(27) == 720


def test_coco_consistency_validator_keeps_partial_results_and_does_not_raise_on_total_timeout(
    monkeypatch,
) -> None:
    async def _fake_validate_checkpoint_via_coco(
        checkpoint,
        mr_context,
        coco_settings,
        llm_client,
        artifact_context=None,
    ):
        del mr_context, coco_settings, llm_client, artifact_context
        if checkpoint.title.endswith("1"):
            await asyncio.sleep(0.01)
            return (
                validator_module.CodeConsistencyResult(
                    status="confirmed",
                    confidence=0.95,
                    actual_implementation="代码与预期一致",
                    verified_by="coco",
                ),
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "checkpoint_title": checkpoint.title,
                },
            )

        await asyncio.sleep(0.20)
        return (
            validator_module.CodeConsistencyResult(
                status="confirmed",
                confidence=0.95,
                actual_implementation="慢任务最终完成",
                verified_by="coco",
            ),
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_title": checkpoint.title,
            },
        )

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_coco",
        _fake_validate_checkpoint_via_coco,
    )
    monkeypatch.setattr(validator_module, "_MAX_CONCURRENCY", 2)
    monkeypatch.setattr(validator_module, "_PER_CASE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(validator_module, "_TOTAL_TIMEOUT_S", 0.05)

    node = build_coco_consistency_validator_node(
        coco_settings=CocoSettings(coco_jwt_token="dummy-token"),
    )

    result = node(
        {
            "checkpoints": [
                Checkpoint(checkpoint_id="CP-1", title="检查点 1"),
                Checkpoint(checkpoint_id="CP-2", title="检查点 2"),
            ],
            "frontend_mr_config": {
                "mr_url": "https://example.com/mr/123",
                "use_coco": True,
                "codebase": {"git_url": "https://example.com/repo.git"},
            },
        }
    )

    assert result["coco_validation_summary"] == {
        "total": 2,
        "confirmed": 1,
        "mismatch": 0,
        "unverified": 1,
    }
    assert result["checkpoints"][0].code_consistency["status"] == "confirmed"
    assert result["checkpoints"][1].code_consistency["status"] == "unverified"
