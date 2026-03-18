"""检查点生成节点。"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.llm import LLMClient
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import GlobalState
from app.domain.template_models import ChecklistTemplate

logger = logging.getLogger(__name__)


CHECKPOINT_SYSTEM_PROMPT = """你是一个专业的测试检查点生成专家。
根据提供的需求事实（facts），生成结构化的测试检查点（checkpoints）。

每个检查点应该包含：
- title: 简洁明确的标题
- objective: 测试目标描述
- category: 分类（functional / security / performance / usability / compatibility / edge_case）
- priority: 优先级（critical / high / medium / low）
- fact_ids: 关联的事实 ID 列表
- verification_criteria: 验证标准列表
"""

CHECKPOINT_USER_PROMPT_TEMPLATE = """## 需求事实

{facts_text}

## 场景规划

{scenarios_text}

请根据以上信息生成测试检查点列表。确保：
1. 每个关键事实都有对应的检查点覆盖
2. 覆盖正向和反向测试场景
3. 每个检查点的目标明确、可验证

输出 JSON 格式的检查点数组。
"""


def build_checkpoint_generator(llm_client: LLMClient):
    """构建检查点生成节点函数。"""

    async def checkpoint_generator(state: GlobalState) -> dict[str, Any]:
        """生成测试检查点。"""
        facts = state.get("facts", [])
        scenarios = state.get("scenarios", [])

        if not facts:
            logger.warning("无可用事实，跳过检查点生成")
            return {"checkpoints": []}

        # 格式化事实
        facts_text = "\n".join(
            f"- [{f.fact_id}] {f.description}" for f in facts
        )

        # 格式化场景
        scenarios_text = "\n".join(
            f"- {s.title} ({s.category}, risk={s.risk})" for s in scenarios
        )

        user_prompt = CHECKPOINT_USER_PROMPT_TEMPLATE.format(
            facts_text=facts_text,
            scenarios_text=scenarios_text,
        )

        # ---- 项目上下文 ----
        project_ctx = state.get("project_context")
        if project_ctx:
            user_prompt += f"\n\n## 项目上下文\n{project_ctx.summary_text()}"

        # ---- 模板驱动生成支持 ----
        # 如果状态中携带了模板数据，将模板维度信息注入提示词，
        # 引导 LLM 按照模板定义的测试维度生成检查点。
        template_dict = state.get("template")
        if template_dict:
            try:
                tpl = ChecklistTemplate.model_validate(template_dict)
                user_prompt += tpl.format_for_checkpoint_prompt()
                logger.info("已注入模板维度到检查点生成提示 (template=%s)", tpl.name)
            except Exception:
                logger.warning("模板数据解析失败，跳过模板注入", exc_info=True)

        # LLM 调用
        checkpoints_data = await llm_client.structured_output(
            system_prompt=CHECKPOINT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=list[dict],
        )

        # 解析为 Checkpoint 对象
        checkpoints = []
        for cp_data in checkpoints_data:
            try:
                cp = Checkpoint.model_validate(cp_data)
                if not cp.checkpoint_id:
                    cp.checkpoint_id = cp.compute_id()
                checkpoints.append(cp)
            except Exception:
                logger.warning("跳过无效检查点: %s", cp_data)

        logger.info("生成 %d 个检查点", len(checkpoints))
        return {"checkpoints": checkpoints}

    return checkpoint_generator
