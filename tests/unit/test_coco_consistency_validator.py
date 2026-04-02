"""Unit tests for coco consistency validator node."""

from __future__ import annotations

from app.config.settings import CocoSettings
from app.domain.checkpoint_models import Checkpoint
from app.nodes import coco_consistency_validator as validator_module
from app.nodes.coco_consistency_validator import build_coco_consistency_validator_node


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
    ):
        del checkpoint, mr_context, coco_settings, llm_client
        return validator_module.CodeConsistencyResult(
            status="confirmed",
            confidence=0.95,
            actual_implementation="代码与预期一致",
            verified_by="coco",
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
    assert result["checkpoints"][0].code_consistency.status == "confirmed"
