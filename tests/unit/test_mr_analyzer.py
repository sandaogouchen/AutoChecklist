"""Unit tests for MR analyzer node."""

from __future__ import annotations

import json

import pytest

from app.domain.mr_models import CodebaseSource, MRDiffFile, MRInput, MRSourceConfig
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
    ("config_key", "result_key", "summary_prefix"),
    [
        ("frontend_mr_config", "frontend_mr_result", "[前端]"),
        ("backend_mr_config", "backend_mr_result", "[后端]"),
    ],
)
def test_mr_analyzer_runs_local_analysis_synchronously(
    config_key: str,
    result_key: str,
    summary_prefix: str,
) -> None:
    node = build_mr_analyzer_node(llm_client=_LocalAnalysisLLM())
    state = {
        config_key: MRSourceConfig(
            mr_url="https://example.com/mr/123",
            codebase=CodebaseSource(local_path=""),
            use_coco=False,
        ),
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
