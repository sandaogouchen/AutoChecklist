"""Draft Writer 节点。

负责将 checkpoint + outline 路径信息交给 LLM，生成测试用例草稿。
每个 checkpoint 产出一个 TestCase 草稿，包含 steps / preconditions /
expected_results / priority / category 等字段。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一名专业的 QA 测试用例撰写专家。
根据给定的 checkpoint 信息和固定层级路径（Fixed hierarchy path），
为每个 checkpoint 编写一条完整的测试用例。

每条用例需要包含以下字段：
- title: 测试用例标题，简洁明了
- steps: 测试步骤，用有序列表描述每一步操作
- preconditions: 前置条件，描述执行该用例前需要满足的状态
- expected_results: 预期结果，描述每一步操作后的预期表现
- priority: 优先级，取值为 P0 / P1 / P2 / P3
- category: 用例类型，取值为 功能测试 / 边界测试 / 异常测试 / 兼容性测试

编写原则：
1. 原子性：每条用例只验证一个功能点
2. 可执行性：步骤描述必须具体、无歧义，新人也能执行
3. 可验证性：预期结果必须可观察、可度量
4. 独立性：用例之间互不依赖，可以独立执行
5. 复用意识：如果多个 checkpoint 共享前置步骤，应抽取到 preconditions 中

【路径与步骤衔接规范】

路径层级（Fixed hierarchy path）已包含操作动词描述的操作序列。
生成 steps 时请遵守以下规则：

1. 衔接性：steps 的第一步应与路径最后一个节点的操作语义自然衔接，
   形成连贯的操作链路。
2. 不重复：路径中已描述的操作（如"进入 XX 页面"、"选择 XX 目标"）不需要在 steps 中重复。
3. 聚焦细节：steps 应聚焦于路径未覆盖的具体交互细节，
   如"展开下拉框"、"输入数值"、"点击确认按钮"、"等待页面加载完成"等。
4. 操作可执行性：每个 step 必须是一个具体的、可执行的操作指令，
   而非抽象描述。
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

_USER_PROMPT_TEMPLATE = """\
Checkpoint:
- ID: {checkpoint_id}
- Title: {title}
- Description: {description}

Fixed hierarchy path:
{path}

请生成测试用例，以 JSON 格式输出，包含 title, steps, preconditions, \
expected_results, priority, category 字段。
"""


# ---------------------------------------------------------------------------
# Draft writer node
# ---------------------------------------------------------------------------


class DraftWriterNode:
    """LangGraph node that generates test-case drafts from checkpoints."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def __call__(self, state: CaseGenState) -> dict[str, Any]:
        """Process all checkpoints in *state* and return draft test cases."""
        checkpoints: Sequence[Checkpoint] = state.get("checkpoints", [])
        path_mappings = state.get("path_mappings", {})
        outline_nodes = state.get("outline_nodes", {})

        drafts: list[TestCase] = []
        for cp in checkpoints:
            path_display = self._format_path(cp.id, path_mappings, outline_nodes)
            draft = await self._generate_draft(cp, path_display)
            if draft:
                drafts.append(draft)

        return {"draft_test_cases": drafts}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_draft(
        self, checkpoint: Checkpoint, path_display: str
    ) -> TestCase | None:
        """Call the LLM to produce a single test-case draft."""
        user_msg = _USER_PROMPT_TEMPLATE.format(
            checkpoint_id=checkpoint.id,
            title=checkpoint.title,
            description=checkpoint.description or "",
            path=path_display,
        )

        try:
            response = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=user_msg,
                response_format="json",
            )
            data = json.loads(response)
            return TestCase(
                id=f"draft_{checkpoint.id}",
                title=data.get("title", checkpoint.title),
                steps=data.get("steps", ""),
                preconditions=data.get("preconditions", ""),
                expected_results=data.get("expected_results", ""),
                priority=data.get("priority", "P2"),
                category=data.get("category", "功能测试"),
                checkpoint_id=checkpoint.id,
            )
        except Exception:
            logger.exception("Failed to generate draft for checkpoint %s", checkpoint.id)
            return None

    @staticmethod
    def _format_path(
        checkpoint_id: str,
        path_mappings: dict[str, list[str]],
        outline_nodes: dict[str, Any],
    ) -> str:
        """Build a human-readable path string for the user prompt."""
        path_ids = path_mappings.get(checkpoint_id, [])
        if not path_ids:
            return "(no path available)"

        segments = []
        for pid in path_ids:
            node = outline_nodes.get(pid)
            if node:
                display = getattr(node, "display_text", pid)
                segments.append(display)
            else:
                segments.append(pid)

        return " → ".join(segments)
