"""Unit tests for MR analyzer node."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from app.domain.mr_models import (
    CodebaseSource,
    MRAnalysisResult,
    MRCodeFact,
    MRDiffFile,
    MRInput,
    MRSourceConfig,
)
from app.domain.research_models import ResearchFact, ResearchOutput
from app.nodes import mr_analyzer as mr_analyzer_module
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


def test_mr_analyzer_runs_single_coco_task_and_keeps_research_output_unchanged(monkeypatch) -> None:
    from app.services import coco_client as coco_client_module

    calls: list[dict[str, str]] = []

    async def _fake_run_mr_analysis_task(self, *, mr_context, prd_summary, changed_files_summary):
        del self
        calls.append(
            {
                "mr_url": mr_context["mr_url"],
                "branch": mr_context["branch"],
                "prd_summary": prd_summary,
                "changed_files_summary": changed_files_summary,
            }
        )
        await asyncio.sleep(0.01)
        return (
            MRAnalysisResult(
                mr_summary="提取到 Pulse lineup 的排期与频控改动",
                changed_modules=["schedule", "frequency-cap"],
                code_facts=[
                    MRCodeFact(
                        fact_id="MR-FACT-001",
                        description="Custom lineup 最短天数校验调整为 7 天",
                        source_file="apps/rf-creation/src/constants/schedule-budget.ts",
                        fact_type="boundary",
                    ),
                    MRCodeFact(
                        fact_id="MR-FACT-002",
                        description="Custom lineup 默认 frequency cap 调整为 4/1",
                        source_file="apps/rf-creation/src/constants/frequency.ts",
                        fact_type="state_change",
                    ),
                ],
            ),
            {"task_id": "task-mr-analysis"},
        )

    monkeypatch.setattr(
        coco_client_module.CocoClient,
        "run_mr_analysis_task",
        _fake_run_mr_analysis_task,
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

    assert len(calls) == 1
    assert calls[0]["mr_url"] == "https://example.com/mr/123"
    assert calls[0]["branch"] == "feat/pulse-setup"
    assert "FACT-001" in calls[0]["prd_summary"]
    assert "FACT-002" in calls[0]["prd_summary"]
    assert elapsed < 0.1
    assert len(result["mr_code_facts"]) == 2
    assert result["mr_consistency_issues"] == []
    assert result["research_output"] is state["research_output"]
    assert result["research_output"].facts[0].code_todo == ""
    assert result["research_output"].facts[1].code_consistency_status == ""


def test_mr_analyzer_runs_frontend_and_backend_in_parallel(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_analyze_single_side(
        *,
        side,
        mr_config,
        state,
        llm_client,
        codebase_root,
        coco_settings,
        prefix,
    ):
        del mr_config, state, llm_client, codebase_root, coco_settings, prefix
        calls.append(side)
        time.sleep(0.05)
        return MRAnalysisResult(
            mr_summary=f"{side} summary",
            changed_modules=[side],
            code_facts=[
                MRCodeFact(
                    fact_id=f"{side}-fact",
                    description=f"{side} fact",
                    source_file=f"{side}.py",
                )
            ],
        )

    monkeypatch.setattr("app.nodes.mr_analyzer._analyze_single_side", _fake_analyze_single_side)

    node = build_mr_analyzer_node(llm_client=object())
    state = {
        "frontend_mr_config": MRSourceConfig(
            mr_url="https://example.com/mr/frontend",
            codebase=CodebaseSource(local_path=""),
            use_coco=False,
        ),
        "backend_mr_config": MRSourceConfig(
            mr_url="https://example.com/mr/backend",
            codebase=CodebaseSource(local_path=""),
            use_coco=False,
        ),
    }

    started = time.monotonic()
    result = node(state)
    elapsed = time.monotonic() - started

    assert set(calls) == {"frontend", "backend"}
    assert elapsed < 0.09
    assert len(result["mr_code_facts"]) == 2
    assert "[前端] frontend summary" in result["mr_combined_summary"]
    assert "[后端] backend summary" in result["mr_combined_summary"]


def test_mr_analyzer_reuses_cached_coco_task1_result(monkeypatch, tmp_path: Path) -> None:
    from app.services import coco_client as coco_client_module

    async def _fail_run_mr_analysis_task(self, *, mr_context, prd_summary, changed_files_summary):
        del self, mr_context, prd_summary, changed_files_summary
        raise AssertionError("should not call Coco when cache is available")

    monkeypatch.setattr(
        coco_client_module.CocoClient,
        "run_mr_analysis_task",
        _fail_run_mr_analysis_task,
    )

    cache_dir = tmp_path / "cached-run" / "coco"
    cache_dir.mkdir(parents=True)
    (cache_dir / "task1_frontend_result.json").write_text(
        json.dumps(
            {
                "mr_summary": "缓存的前端 MR 摘要",
                "changed_modules": ["auth"],
                "related_code_snippets": [],
                "code_facts": [
                    {
                        "fact_id": "MR-FACT-001",
                        "description": "缓存的代码事实",
                        "source_file": "app/auth.py",
                        "code_snippet": "if not token: return fallback",
                        "fact_type": "error_handling",
                        "related_prd_fact_ids": ["FACT-001"],
                    }
                ],
                "consistency_issues": [],
                "search_trace": ["via_coco_cache"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    node = build_mr_analyzer_node(
        llm_client=object(),
        coco_settings=type("CocoSettings", (), {"coco_jwt_token": ""})(),
    )
    result = node(
        {
            "frontend_mr_config": MRSourceConfig(
                mr_url="https://example.com/mr/123",
                codebase=CodebaseSource(
                    git_url="https://example.com/repo.git",
                    branch="feat/pulse-setup",
                ),
                use_coco=True,
            ),
            "coco_cache_dir": str(cache_dir),
            "research_output": ResearchOutput(
                facts=[ResearchFact(fact_id="FACT-001", description="登录失败时应明确提示用户原因")]
            ),
        }
    )

    assert result["mr_code_facts"][0].fact_id == "FE-MR-FACT-001"
    assert result["mr_code_facts"][0].description == "缓存的代码事实"


def test_mr_analyzer_routes_remote_analysis_to_mira_when_enabled(monkeypatch) -> None:
    calls: list[dict[str, str]] = []

    async def _fake_analyze_via_mira(
        mr_config,
        state,
        llm_client,
        prefix,
        side,
    ):
        del state, llm_client
        calls.append(
            {
                "mr_url": mr_config.mr_url,
                "prefix": prefix,
                "side": side,
            }
        )
        return MRAnalysisResult(
            mr_summary="Mira 代码分析摘要",
            code_facts=[
                MRCodeFact(
                    fact_id="MR-FACT-001",
                    description="Mira 发现的代码事实",
                    source_file="app/mira.py",
                )
            ],
        )

    async def _fail_analyze_via_coco(
        mr_config,
        state,
        llm_client,
        coco_settings,
        prefix,
        side,
    ):
        del mr_config, state, llm_client, coco_settings, prefix, side
        raise AssertionError("should not call Coco when Mira code analysis is enabled")

    monkeypatch.setattr("app.nodes.mr_analyzer._analyze_via_mira", _fake_analyze_via_mira)
    monkeypatch.setattr("app.nodes.mr_analyzer._analyze_via_coco", _fail_analyze_via_coco)

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

    node = build_mr_analyzer_node(llm_client=llm_client)
    result = node(
        {
            "frontend_mr_config": MRSourceConfig(
                mr_url="https://example.com/mr/456",
                codebase=CodebaseSource(git_url="https://example.com/repo.git"),
                use_coco=True,
            ),
            "mr_input": MRInput(diff_files=[]),
            "research_output": ResearchOutput(),
        }
    )

    assert calls == [
        {
            "mr_url": "https://example.com/mr/456",
            "prefix": "FE-",
            "side": "frontend",
        }
    ]
    assert result["mr_combined_summary"] == "[前端] Mira 代码分析摘要"
    assert result["mr_code_facts"][0].description == "Mira 发现的代码事实"


def test_analyze_via_mira_persists_artifacts_under_mira_dir(monkeypatch, tmp_path: Path) -> None:
    class _FakeMiraAnalysisService:
        def __init__(self, llm_client) -> None:
            del llm_client

        async def run_mr_analysis_task(self, *, mr_context, prd_summary, changed_files_summary):
            del mr_context, prd_summary, changed_files_summary
            return (
                MRAnalysisResult(
                    mr_summary="Mira 分析结果",
                    code_facts=[
                        MRCodeFact(
                            fact_id="MR-FACT-001",
                            description="Mira fact",
                            source_file="app/mira.py",
                        )
                    ],
                ),
                {
                    "prompt": "prompt body",
                    "task": {"session_id": "mira-session"},
                },
            )

    monkeypatch.setattr(
        mr_analyzer_module,
        "MiraAnalysisService",
        _FakeMiraAnalysisService,
    )

    state = {
        "run_output_dir": str(tmp_path),
        "mr_input": MRInput(diff_files=[]),
        "research_output": ResearchOutput(),
    }
    result = asyncio.run(
        mr_analyzer_module._analyze_via_mira(
            MRSourceConfig(
                mr_url="https://example.com/mr/456",
                codebase=CodebaseSource(
                    git_url="https://example.com/repo.git",
                    branch="feat/mira-artifacts",
                ),
                use_coco=True,
            ),
            state,
            object(),
            "FE-",
            "frontend",
        )
    )

    prompt_path = tmp_path / "mira" / "task1_frontend_prompt.txt"
    task_path = tmp_path / "mira" / "task1_frontend_task.json"
    result_path = tmp_path / "mira" / "task1_frontend_result.json"

    assert result.mr_summary == "Mira 分析结果"
    assert prompt_path.exists()
    assert task_path.exists()
    assert result_path.exists()
    assert not (tmp_path / "coco" / "task1_frontend_result.json").exists()
    assert state["mira_artifacts"]["task1_frontend_result"] == str(result_path)
