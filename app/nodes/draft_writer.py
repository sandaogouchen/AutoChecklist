"""用例草稿生成节点。"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState
from app.domain.template_models import ChecklistTemplate

logger = logging.getLogger(__name__)


DRAFT_SYSTEM_PROMPT = """你是一个专业的测试用例撰写专家。
根据提供的检查点信息，为每个检查点生成详细的测试用例。

每个测试用例应包含：
- id: 编号（如 TC-001）
- title: 用例标题
- preconditions: 前置条件列表
- steps: 操作步骤列表
- expected_results: 预期结果列表
- priority: 优先级（P0-P3）
- category: 分类
- checkpoint_id: 关联的检查点 ID
"""


def build_draft_writer(llm_client: LLMClient):
    """构建用例草稿生成节点函数。"""

    async def draft_writer(state: CaseGenState) -> dict[str, Any]:
        """为每个检查点生成测试用例草稿。"""
        checkpoints = state.get("checkpoints", [])
        language = state.get("language", "en")

        if not checkpoints:
            logger.warning("无可用检查点，跳过用例生成")
            return {"test_cases": []}

        # ---- 预加载模板对象（如果存在） ----
        template_obj: ChecklistTemplate | None = None
        template_dict = state.get("template")
        if template_dict:
            try:
                template_obj = ChecklistTemplate.model_validate(template_dict)
                logger.info("用例草稿生成已启用模板引导 (template=%s)", template_obj.name)
            except Exception:
                logger.warning("模板数据解析失败，降级为无模板模式", exc_info=True)

        all_cases: list[TestCase] = []

        for checkpoint in checkpoints:
            user_prompt = _build_checkpoint_prompt(checkpoint, language)

            # ---- 模板驱动生成支持 ----
            # 如果检查点关联了模板维度，使用结构化模板提示替代简单文本拼接。
            # 模板提示会包含该维度下的具体要求和检查条目，引导 LLM
            # 生成更贴合模板规范的测试用例。
            if template_obj and (checkpoint.template_category or checkpoint.template_item_title):
                try:
                    template_prompt = template_obj.format_for_draft_prompt(
                        template_category=checkpoint.template_category,
                        template_item_title=checkpoint.template_item_title,
                    )
                    user_prompt += template_prompt
                except Exception:
                    logger.warning(
                        "模板草稿提示构建失败 (category=%s, item=%s)，跳过模板注入",
                        checkpoint.template_category,
                        checkpoint.template_item_title,
                        exc_info=True,
                    )

            # ---- 项目上下文（与模板规则并存时两者都注入） ----
            project_ctx = state.get("project_context")
            if project_ctx:
                user_prompt += f"\n\n## 项目上下文（checklist 模板约束）\n{project_ctx.summary_text()}"

            cases_data = await llm_client.structured_output(
                system_prompt=DRAFT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                output_schema=list[dict],
            )

            for case_data in cases_data:
                try:
                    case = TestCase.model_validate(case_data)
                    case.checkpoint_id = checkpoint.checkpoint_id
                    all_cases.append(case)
                except Exception:
                    logger.warning("跳过无效用例: %s", case_data)

        logger.info("生成 %d 个测试用例草稿", len(all_cases))
        return {"test_cases": all_cases}

    return draft_writer


def _build_checkpoint_prompt(checkpoint: Checkpoint, language: str) -> str:
    """构建单个检查点的用例生成提示。"""
    prompt = f"""## 当前检查点
- 标题：{checkpoint.title}
- 目标：{checkpoint.objective}
- 分类：{checkpoint.category}
- 优先级：{checkpoint.priority}

## 语言要求
请使用 {language} 语言撰写测试用例。

请为此检查点生成详细的测试用例，输出 JSON 格式的用例数组。
"""
    return prompt
