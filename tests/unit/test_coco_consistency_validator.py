"""Unit tests for coco consistency validator node."""

from __future__ import annotations

import asyncio
import json

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


def test_coco_consistency_validator_reuses_cached_task2_results(monkeypatch, tmp_path) -> None:
    async def _fail_validate_checkpoint_via_coco(
        checkpoint,
        mr_context,
        coco_settings,
        llm_client,
        artifact_context=None,
    ):
        del checkpoint, mr_context, coco_settings, llm_client, artifact_context
        raise AssertionError("should not call Coco when task2 cache is available")

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_coco",
        _fail_validate_checkpoint_via_coco,
    )

    cache_dir = tmp_path / "cached-run" / "coco"
    cache_dir.mkdir(parents=True)
    (cache_dir / "task2_results.json").write_text(
        json.dumps(
            [
                {
                    "checkpoint_id": "CP-1",
                    "checkpoint_title": "检查点 1",
                    "result": {
                        "status": "confirmed",
                        "confidence": 0.95,
                        "actual_implementation": "缓存命中",
                        "inconsistency_reason": "",
                        "related_code_file": "app/example.py",
                        "related_code_snippet": "return ok",
                        "verified_by": "coco-cache",
                    },
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    node = build_coco_consistency_validator_node(
        coco_settings=CocoSettings(coco_jwt_token=""),
    )

    result = node(
        {
            "checkpoints": [Checkpoint(checkpoint_id="CP-1", title="检查点 1")],
            "coco_cache_dir": str(cache_dir),
            "frontend_mr_config": {
                "mr_url": "https://example.com/mr/123",
                "use_coco": True,
                "codebase": {"git_url": "https://example.com/repo.git"},
            },
        }
    )

    assert result["coco_validation_summary"] == {
        "total": 1,
        "confirmed": 1,
        "mismatch": 0,
        "unverified": 0,
    }
    assert result["checkpoints"][0].code_consistency["verified_by"] == "coco-cache"


def test_coco_consistency_validator_routes_remote_validation_to_mira_when_enabled(
    monkeypatch,
) -> None:
    async def _fake_validate_checkpoint_via_mira(
        checkpoint,
        mr_context,
        llm_client,
        artifact_context=None,
    ):
        del mr_context, llm_client, artifact_context
        return (
            validator_module.CodeConsistencyResult(
                status="mismatch",
                confidence=0.88,
                actual_implementation="Mira 识别到实际实现与预期不同",
                inconsistency_reason="缺少错误提示",
                verified_by="mira",
            ),
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_title": checkpoint.title,
            },
        )

    async def _fail_validate_checkpoint_via_coco(
        checkpoint,
        mr_context,
        coco_settings,
        llm_client,
        artifact_context=None,
    ):
        del checkpoint, mr_context, coco_settings, llm_client, artifact_context
        raise AssertionError("should not call Coco validator when Mira code analysis is enabled")

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_mira",
        _fake_validate_checkpoint_via_mira,
    )
    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_coco",
        _fail_validate_checkpoint_via_coco,
    )

    llm_client = type(
        "FakeLLM",
        (),
        {
            "config": type(
                "Config",
                (),
                {"mira_use_for_code_analysis": True},
            )()
        },
    )()

    node = build_coco_consistency_validator_node(
        llm_client=llm_client,
        coco_settings=CocoSettings(coco_jwt_token="dummy-token"),
    )

    result = node(
        {
            "checkpoints": [Checkpoint(checkpoint_id="CP-9", title="验证错误提示")],
            "frontend_mr_config": {
                "mr_url": "https://example.com/mr/123",
                "use_coco": True,
                "codebase": {"git_url": "https://example.com/repo.git"},
            },
        }
    )

    assert result["coco_validation_summary"] == {
        "total": 1,
        "confirmed": 0,
        "mismatch": 1,
        "unverified": 0,
    }
    assert result["checkpoints"][0].code_consistency["verified_by"] == "mira"


def test_validate_checkpoint_via_mira_persists_detail_under_mira_dir(monkeypatch, tmp_path) -> None:
    class _FakeMiraAnalysisService:
        def __init__(self, llm_client) -> None:
            del llm_client

        async def run_validation_task(self, checkpoint, mr_context):
            del checkpoint, mr_context
            return (
                validator_module.CodeConsistencyResult(
                    status="confirmed",
                    confidence=0.93,
                    actual_implementation="Mira 详情记录",
                    verified_by="mira",
                ),
                {
                    "prompt": "validation prompt",
                    "response": "{\"ok\":true}",
                },
            )

    monkeypatch.setattr(
        validator_module,
        "MiraAnalysisService",
        _FakeMiraAnalysisService,
    )

    result, record = asyncio.run(
        validator_module._validate_checkpoint_via_mira(
            checkpoint=Checkpoint(checkpoint_id="CP-3", title="检查点 3"),
            mr_context={
                "mr_url": "https://example.com/mr/123",
                "git_url": "https://example.com/repo.git",
            },
            llm_client=object(),
            artifact_context={
                "run_output_dir": str(tmp_path),
                "checkpoint_index": 3,
            },
        )
    )

    detail_path = tmp_path / "mira" / "task2_checkpoint_003.json"
    assert result.status == "confirmed"
    assert detail_path.exists()
    assert record["artifact_file"] == str(detail_path)


def test_coco_consistency_validator_persists_mira_summary_under_mira_dir(monkeypatch, tmp_path) -> None:
    async def _fake_validate_checkpoint_via_mira(
        checkpoint,
        mr_context,
        llm_client,
        artifact_context=None,
    ):
        del mr_context, llm_client, artifact_context
        return (
            validator_module.CodeConsistencyResult(
                status="confirmed",
                confidence=0.91,
                actual_implementation="Mira 汇总落盘",
                verified_by="mira",
            ),
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_title": checkpoint.title,
            },
        )

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_mira",
        _fake_validate_checkpoint_via_mira,
    )

    llm_client = type(
        "FakeLLM",
        (),
        {
            "config": type(
                "Config",
                (),
                {"mira_use_for_code_analysis": True},
            )()
        },
    )()

    node = build_coco_consistency_validator_node(
        llm_client=llm_client,
        coco_settings=CocoSettings(coco_jwt_token="dummy-token"),
    )

    result = node(
        {
            "run_output_dir": str(tmp_path),
            "checkpoints": [Checkpoint(checkpoint_id="CP-9", title="验证错误提示")],
            "frontend_mr_config": {
                "mr_url": "https://example.com/mr/123",
                "use_coco": True,
                "codebase": {"git_url": "https://example.com/repo.git"},
            },
        }
    )

    summary_path = tmp_path / "mira" / "task2_summary.json"
    results_path = tmp_path / "mira" / "task2_results.json"
    assert summary_path.exists()
    assert results_path.exists()
    assert not (tmp_path / "coco" / "task2_summary.json").exists()
    assert result["mira_artifacts"]["task2_summary"] == str(summary_path)
