from __future__ import annotations

import asyncio
import time

from app.config.settings import CocoSettings
from app.domain.checkpoint_models import Checkpoint
from app.domain.mr_models import CodeConsistencyResult, MRSourceConfig
from app.nodes import coco_consistency_validator as validator_module
from app.nodes.coco_consistency_validator import build_coco_consistency_validator_node
from app.nodes.mr_analyzer import _build_coco_task1_prompt


def test_task1_prompt_mentions_repo_branch_and_analysis_flow() -> None:
    prompt = _build_coco_task1_prompt(
        mr_url="https://example.com/org/repo/merge_requests/1",
        git_url="https://example.com/org/repo.git",
        branch="feat/pulse-setup",
        prd_summary="场景：创建 Pulse Custom Lineups。预期：Campaign length 最短支持 7 天。",
        changed_files_summary="pulse/settings.py",
    )

    assert "仓库" in prompt
    assert "分支" in prompt
    assert "feat/pulse-setup" in prompt
    assert "先定位与场景相关的模块" in prompt
    assert "再结合代码逻辑判断是否符合预期" in prompt


def test_coco_validator_waits_for_all_tasks_and_persists_outputs(monkeypatch, tmp_path) -> None:
    async def _fake_validate_checkpoint_via_coco(
        checkpoint,
        mr_context,
        coco_settings,
        llm_client,
        artifact_context=None,
    ):
        del mr_context, coco_settings, llm_client
        await asyncio.sleep(0.05 if checkpoint.title.endswith("1") else 0.01)
        return (
            CodeConsistencyResult(
                status="confirmed",
                confidence=0.91,
                actual_implementation=f"{checkpoint.title} OK",
                verified_by="coco",
            ),
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_title": checkpoint.title,
                "artifact_context": artifact_context,
            },
        )

    monkeypatch.setattr(
        validator_module,
        "_validate_checkpoint_via_coco",
        _fake_validate_checkpoint_via_coco,
    )

    node = build_coco_consistency_validator_node(
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    started = time.monotonic()
    result = node(
        {
            "run_id": "run-001",
            "run_output_dir": str(tmp_path / "run-001"),
            "checkpoints": [
                Checkpoint(checkpoint_id="CP-1", title="检查点 1"),
                Checkpoint(checkpoint_id="CP-2", title="检查点 2"),
            ],
            "frontend_mr_config": MRSourceConfig(
                mr_url="https://example.com/org/repo/merge_requests/1",
                codebase={
                    "git_url": "https://example.com/org/repo.git",
                    "branch": "feat/pulse-setup",
                },
                use_coco=True,
            ),
        }
    )
    elapsed = time.monotonic() - started

    assert elapsed >= 0.05
    assert result["coco_validation_summary"]["confirmed"] == 2
    assert (tmp_path / "run-001" / "coco" / "task2_summary.json").exists()
    assert (tmp_path / "run-001" / "coco" / "task2_results.json").exists()
