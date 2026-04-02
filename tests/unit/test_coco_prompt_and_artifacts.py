from __future__ import annotations

import asyncio
import time

from app.config.settings import CocoSettings
from app.domain.checkpoint_models import Checkpoint
from app.domain.mr_models import CodeConsistencyResult, MRSourceConfig
from app.domain.research_models import ResearchFact, ResearchOutput
from app.nodes import coco_consistency_validator as validator_module
from app.nodes.coco_consistency_validator import build_coco_consistency_validator_node
from app.nodes.mr_analyzer import (
    _build_candidate_module_summary,
    _build_coco_task1_prompt,
    _build_coco_task1_prompt_for_fact,
    _build_prd_summary,
    _normalize_codebase_context,
)


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


def test_task1_fact_prompt_focuses_single_fact_and_requests_revision() -> None:
    prompt = _build_coco_task1_prompt_for_fact(
        mr_url="https://example.com/org/repo/merge_requests/1",
        git_url="https://example.com/org/repo.git",
        branch="feat/pulse-setup",
        fact=ResearchFact(
            fact_id="FACT-001",
            description="Campaign length 最短支持 7 天",
            requirement="最短 campaign length 必须从 14 天下调为 7 天",
            branch_hint="边界值校验分支（<7, =7, >7）",
        ),
        changed_files_summary="apps/rf-creation/src/constants/schedule-budget.ts",
    )

    assert "FACT-001" in prompt
    assert "Campaign length 最短支持 7 天" in prompt
    assert "fact_revision" in prompt
    assert '"todo"' in prompt
    assert "Branch: feat/pulse-setup" in prompt


def test_normalize_codebase_context_derives_branch_from_bits_tree_url() -> None:
    git_url, branch = _normalize_codebase_context(
        mr_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/merge_requests/2142",
        git_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/tree/feat-pulse-lineup",
        branch="",
    )

    assert git_url == "https://code.byted.org/ad/ttam_brand_mono.git"
    assert branch == "feat-pulse-lineup"


def test_build_prd_summary_reads_research_output_model_facts() -> None:
    state = {
        "research_output": ResearchOutput(
            facts=[
                ResearchFact(
                    fact_id="FACT-001",
                    description="用户可在 Pulse 页面创建 lineup",
                    requirement="点击 Create lineup 后保存成功并展示在列表中",
                    branch_hint="happy path",
                )
            ]
        )
    }

    summary = _build_prd_summary(state)

    assert "FACT-001" in summary
    assert "Create lineup" in summary
    assert "happy path" in summary


def test_candidate_module_summary_uses_fact_and_checkpoint_context_without_diff() -> None:
    state = {
        "research_output": ResearchOutput(
            facts=[
                ResearchFact(
                    fact_id="FACT-001",
                    description="用户可在 Pulse 页面创建 lineup",
                    requirement="点击 Create lineup 后保存成功并展示在列表中",
                    branch_hint="happy path",
                )
            ]
        ),
        "checkpoints": [
            Checkpoint(
                checkpoint_id="CP-001",
                title="校验创建 lineup 成功",
                objective="新建成功后列表展示新建 lineup",
                preconditions=["已选择 Brand", "已填写 lineup 名称"],
            )
        ],
    }

    summary = _build_candidate_module_summary(state, diff_files=[])

    assert "FACT-001" in summary
    assert "Create lineup" in summary
    assert "校验创建 lineup 成功" in summary
    assert "已选择 Brand" in summary
    assert "无显式变更文件摘要" not in summary


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
