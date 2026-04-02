"""Unit tests for MR analyzer node."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.domain.mr_models import (
    CodebaseSource,
    ConsistencyIssue,
    MRAnalysisResult,
    MRCodeFact,
    MRDiffFile,
    MRInput,
    MRSourceConfig,
)
from app.domain.research_models import ResearchFact, ResearchOutput
from app.nodes.mr_analyzer import build_mr_analyzer_node


class _LocalAnalysisLLM:
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature=None,
        max_tokens=None,
    ) -> str:
        del system_prompt, temperature, max_tokens

        if "[变更文件列表]" in user_prompt:
            return json.dumps(
                {
                    "mr_summary": "更新登录逻辑",
                    "changed_modules": ["auth"],
                },
                ensure_ascii=False,
            )

        if "任务 A — 代码级 Fact 提取" in user_prompt:
            return json.dumps(
                {
                    "code_facts": [
                        {
                            "description": "新增登录失败分支",
                            "source_file": "app/auth.py",
                            "code_snippet": "if not token: raise ValueError",
                            "fact_type": "error_handling",
                            "related_prd_fact_ids": [],
                        }
                    ],
                    "consistency_issues": [
                        {
                            "severity": "warning",
                            "prd_expectation": "登录失败时提示原因",
                            "mr_implementation": "登录失败时抛出异常",
                            "discrepancy": "提示方式不同",
                            "affected_file": "app/auth.py",
                            "recommendation": "补充错误提示",
                            "confidence": 0.8,
                        }
                    ],
                },
                ensure_ascii=False,
            )

        raise AssertionError(f"unexpected prompt: {user_prompt[:120]}")


def test_mr_analyzer_returns_empty_dict_without_mr_input() -> None:
    node = build_mr_analyzer_node(llm_client=object())

    result = node({"language": "zh-CN"})

    assert result == {}
    assert isinstance(result, dict)


@pytest.mark.parametrize(
    ("config_key", "result_key", "summary_prefix", "as_dict"),
    [
        ("frontend_mr_config", "frontend_mr_result", "[前端]", False),
        ("frontend_mr_config", "frontend_mr_result", "[前端]", True),
        ("backend_mr_config", "backend_mr_result", "[后端]", False),
        ("backend_mr_config", "backend_mr_result", "[后端]", True),
    ],
)
def test_mr_analyzer_runs_local_analysis_synchronously(
    config_key: str,
    result_key: str,
    summary_prefix: str,
    as_dict: bool,
) -> None:
    node = build_mr_analyzer_node(llm_client=_LocalAnalysisLLM())
    config = MRSourceConfig(
        mr_url="https://example.com/mr/123",
        codebase=CodebaseSource(local_path=""),
        use_coco=False,
    )
    state = {
        config_key: config.model_dump(mode="json") if as_dict else config,
        "mr_input": MRInput(
            mr_title="登录逻辑修复",
            mr_description="修复 token 缺失时的异常路径",
            diff_files=[
                MRDiffFile(
                    file_path="app/auth.py",
                    change_type="modified",
                    diff_content="+ def login(user):\n+     if not token:\n+         raise ValueError('missing')",
                    additions=3,
                    deletions=0,
                )
            ],
        ),
        "research_output": {
            "facts": [
                {"description": "登录失败时应明确提示用户原因"},
            ]
        },
    }

    result = node(state)

    assert isinstance(result, dict)
    assert result["mr_combined_summary"] == f"{summary_prefix} 更新登录逻辑"
    assert len(result["mr_code_facts"]) == 1
    assert result["mr_code_facts"][0].fact_type == "error_handling"
    assert len(result["mr_consistency_issues"]) == 1
    assert result[result_key].mr_summary == "更新登录逻辑"


def test_mr_analyzer_runs_one_coco_task_per_fact_and_updates_fact_todo(monkeypatch) -> None:
    from app.services import coco_client as coco_client_module

    calls: list[str] = []

    async def _fake_run_mr_fact_task(self, *, fact, mr_context, changed_files_summary):
        del self, mr_context, changed_files_summary
        calls.append(fact.fact_id)
        await asyncio.sleep(0.05 if fact.fact_id == "FACT-001" else 0.01)

        if fact.fact_id == "FACT-001":
            return (
                MRAnalysisResult(
                    mr_summary="更新 campaign length 校验",
                    changed_modules=["schedule"],
                    code_facts=[
                        MRCodeFact(
                            fact_id="MR-FACT-001",
                            description="Custom lineup 最短天数校验调整为 7 天",
                            source_file="apps/rf-creation/src/constants/schedule-budget.ts",
                            fact_type="boundary",
                            related_prd_fact_ids=["FACT-001"],
                        )
                    ],
                ),
                coco_client_module.Task1FactRevisionItem(
                    fact_id="FACT-001",
                    status="confirmed",
                    confidence=0.94,
                ),
                {"task_id": "task-fact-001"},
            )

        return (
            MRAnalysisResult(
                mr_summary="frequency cap 默认值仍未更新",
                changed_modules=["frequency-cap"],
                code_facts=[
                    MRCodeFact(
                        fact_id="MR-FACT-002",
                        description="Custom lineup frequency cap 默认值仍为 3/7days",
                        source_file="apps/rf-creation/src/constants/frequency.ts",
                        fact_type="state_change",
                        related_prd_fact_ids=["FACT-002"],
                    )
                ],
                consistency_issues=[
                    ConsistencyIssue(
                        issue_id="CONSIST-001",
                        severity="major",
                        prd_expectation="默认 frequency cap 必须为 4 impressions per 1 day",
                        mr_implementation="当前默认 frequency cap 仍为 3 impressions per 7 days",
                        discrepancy="默认值未按需求更新",
                        confidence=0.93,
                    )
                ],
            ),
            coco_client_module.Task1FactRevisionItem(
                fact_id="FACT-002",
                status="mismatch",
                todo="代码当前默认值仍为 3 impressions per 7 days，生成 checklist 时保留 TODO 并覆盖默认值与提交流程",
                actual_implementation="UI 默认 frequency cap 仍展示为 3 impressions per 7 days",
                confidence=0.93,
            ),
            {"task_id": "task-fact-002"},
        )

    monkeypatch.setattr(
        coco_client_module.CocoClient,
        "run_mr_fact_task",
        _fake_run_mr_fact_task,
    )

    node = build_mr_analyzer_node(
        llm_client=object(),
        coco_settings=type("CocoSettings", (), {"coco_jwt_token": "token"})(),
    )
    state = {
        "frontend_mr_config": MRSourceConfig(
            mr_url="https://example.com/mr/123",
            codebase=CodebaseSource(
                git_url="https://example.com/repo.git",
                branch="feat/pulse-setup",
            ),
            use_coco=True,
        ),
        "mr_input": MRInput(
            diff_files=[
                MRDiffFile(
                    file_path="apps/rf-creation/src/constants/frequency.ts",
                    change_type="modified",
                    additions=2,
                    deletions=2,
                )
            ],
        ),
        "research_output": ResearchOutput(
            facts=[
                ResearchFact(
                    fact_id="FACT-001",
                    description="Pulse Custom Lineups 的最短 campaign length 从 14 天下调为 7 天",
                    requirement="最短 campaign length 必须改为 7 天",
                ),
                ResearchFact(
                    fact_id="FACT-002",
                    description="Pulse Custom Lineups 的默认 frequency cap 改为 4 impressions per day",
                    requirement="默认 frequency cap 必须为 4 impressions per 1 day",
                ),
            ]
        ),
    }

    started = time.monotonic()
    result = node(state)
    elapsed = time.monotonic() - started

    assert calls == ["FACT-001", "FACT-002"]
    assert elapsed < 0.1
    assert len(result["mr_code_facts"]) == 2
    assert result["research_output"].facts[0].code_todo == ""
    assert "3 impressions per 7 days" in result["research_output"].facts[1].code_todo
    assert result["research_output"].facts[1].code_consistency_status == "mismatch"
