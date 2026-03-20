"""Logging tests for checklist integration and template binding."""

from __future__ import annotations

import logging

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchFact, ResearchOutput
from app.domain.template_models import TemplateLeafTarget
from app.nodes.checkpoint_generator import build_checkpoint_generator_node
from app.nodes.structure_assembler import structure_assembler_node


def _reset_app_logging_for_caplog() -> None:
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.setLevel(logging.NOTSET)
    app_logger.propagate = True


class _TemplateBindingLLM:
    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        return response_model.model_validate(
            {
                "checkpoints": [
                    {
                        "title": "验证成功绑定模版",
                        "fact_ids": ["FACT-001"],
                        "template_leaf_id": "leaf-login-success",
                        "template_match_confidence": 0.82,
                        "template_match_reason": "该检查点验证登录成功主路径",
                    },
                    {
                        "title": "验证无效模版绑定",
                        "fact_ids": ["FACT-001"],
                        "template_leaf_id": "leaf-missing",
                        "template_match_confidence": 0.91,
                        "template_match_reason": "模型误选了不存在的叶子",
                    },
                    {
                        "title": "验证未绑定模版",
                        "fact_ids": ["FACT-001"],
                        "template_leaf_id": "",
                        "template_match_confidence": 0.0,
                        "template_match_reason": "没有合适的叶子节点",
                    },
                ]
            }
        )


def test_checkpoint_generator_logs_template_binding_process(caplog) -> None:
    _reset_app_logging_for_caplog()
    node = build_checkpoint_generator_node(_TemplateBindingLLM())
    state = {
        "language": "zh-CN",
        "research_output": ResearchOutput(
            facts=[
                ResearchFact(
                    fact_id="FACT-001",
                    description="用户可以成功登录系统",
                    category="behavior",
                )
            ]
        ),
        "template_leaf_targets": [
            TemplateLeafTarget(
                leaf_id="leaf-login-success",
                leaf_title="成功登录",
                path_ids=["root-login", "leaf-login-success"],
                path_titles=["登录", "成功登录"],
                path_text="登录 > 成功登录",
            )
        ],
    }

    with caplog.at_level(logging.INFO, logger="app.nodes.checkpoint_generator"):
        result = node(state)

    assert len(result["checkpoints"]) == 3
    assert "Template binding enabled for checkpoint generation" in caplog.text
    assert "LLM chooses one template leaf id" in caplog.text
    assert "status=bound" in caplog.text
    assert "status=invalid_leaf_id_cleared" in caplog.text
    assert "status=unbound" in caplog.text
    assert "Template binding summary" in caplog.text


def test_structure_assembler_logs_checklist_summary_before_integration(caplog) -> None:
    _reset_app_logging_for_caplog()
    state = {
        "draft_cases": [
            TestCase(
                id="draft-1",
                title="验证登录成功",
                checkpoint_id="CP-001",
                preconditions=["用户已登录后台"],
                steps=["点击 `Submit`"],
                expected_results=["页面展示成功提示"],
            )
        ],
        "checkpoints": [
            Checkpoint(
                checkpoint_id="CP-001",
                title="验证登录成功",
                template_leaf_id="leaf-login-success",
                template_path_ids=["root-login", "leaf-login-success"],
                template_path_titles=["登录", "成功登录"],
                template_match_confidence=0.82,
                template_match_reason="该检查点验证登录成功主路径",
            )
        ],
        "optimized_tree": [],
        "checkpoint_paths": [],
        "canonical_outline_nodes": [],
    }

    with caplog.at_level(logging.INFO, logger="app.nodes.structure_assembler"):
        result = structure_assembler_node(state)

    assert result["test_cases"][0].template_leaf_id == "leaf-login-success"
    assert "Checklist template inheritance" in caplog.text
    assert "Checklist integration starting" in caplog.text
    assert "Checklist pre-integration item" in caplog.text
