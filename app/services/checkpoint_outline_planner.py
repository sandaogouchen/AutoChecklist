"""Checkpoint outline 规划服务。

支持双模式 XMind 参考注入：
- 模式1（仅参考无模版）：XMind 骨架为主结构锚点，“必须尽量遵循”
- 模式2（模版+参考）：强制骨架为硬约束 + 参考辅助 checkpoint 路由 + 非强制区域按参考组织
"""

import json
import logging
import re

from app.services.llm_client import call_llm
from app.prompts.checkpoint_outline_planner_prompt import CHECKPOINT_OUTLINE_PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def extract_json_from_response(response_text: str):
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in markdown code blocks first
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = response_text.strip()

    return json.loads(json_str)


def _get_formatted_summary(xmind_reference_summary) -> str:
    """Safely extract formatted_summary from Pydantic model or dict."""
    if xmind_reference_summary is None:
        return ""
    if hasattr(xmind_reference_summary, "formatted_summary"):
        return xmind_reference_summary.formatted_summary or ""
    if isinstance(xmind_reference_summary, dict):
        return xmind_reference_summary.get("formatted_summary", "")
    return ""


def _build_xmind_reference_prompt_section(
    xmind_reference_summary,
    has_mandatory_skeleton: bool,
    routing_hints: str = "",
) -> str:
    """构建 XMind 参考的 prompt 注入段落。

    双模式 prompt 策略：
    - 模式1（仅参考无模版）: XMind 骨架为主结构锚点，“必须尽量遵循此结构”
    - 模式2（模版+参考）: 强制骨架为硬约束 + 参考辅助 checkpoint 路由 + 非强制区域按参考组织
    """
    formatted = _get_formatted_summary(xmind_reference_summary)
    if not formatted:
        return ""

    if not has_mandatory_skeleton:
        # 模式1: 仅有参考，无强制模版 → 参考作为主结构锚点
        return (
            "\n\n## 参考 Checklist 结构（主结构锚点）\n"
            f"{formatted}\n"
            "【重要指令】你生成的 outline 必须尽量遵循此参考结构的覆盖维度和组织方式。\n"
            "- 参考结构中的一级分支应作为你输出的主要分类维度\n"
            "- 参考结构中的二级分支应作为子分类的参考\n"
            "- 命名风格和路径组织方式应与参考保持一致\n"
            "- 仅在参考结构明显未覆盖的领域，可自行补充新的分支\n"
        )

    # 模式2: 有强制模版 + 有参考 → 参考作为路由辅助 + 补充锚点
    section = (
        "\n\n## 参考 Checklist 结构（路由辅助 + 补充锚点）\n"
        f"{formatted}\n"
        "【重要指令】强制模版骨架中标记为“必须保留”的节点是硬约束，不可更改。\n"
        "参考结构用于以下用途：\n"
        "- **路由辅助**：根据参考结构判断每个 checkpoint 最适合归属到哪个强制节点下\n"
        "- **补充锚点**：强制模版未覆盖的区域，按参考结构的组织方式补充分支\n"
        "- **风格对齐**：命名风格和层级深度参考已有结构\n"
    )
    if routing_hints:
        section += (
            "\n## Checkpoint 归属建议\n"
            "以下是基于参考结构的 checkpoint 路由建议：\n"
            f"{routing_hints}\n"
        )
    return section


def plan_checkpoint_outline(
    doc_content: str,
    doc_type: str,
    model: str = "gpt-4o",
    xmind_reference_summary=None,
    mandatory_skeleton=None,
    checkpoint_titles: list[str] | None = None,
) -> dict:
    """Plan checkpoint outline based on document content and type.

    Supports dual-mode XMind reference injection:
    - Mode 1 (reference only, no template): XMind skeleton = primary structural anchor
    - Mode 2 (template + reference): mandatory skeleton = hard constraint,
      reference = routing assistant + supplementary anchor

    Args:
        doc_content: Document content to analyze.
        doc_type: Type of the document.
        model: LLM model identifier.
        xmind_reference_summary: Optional ``XMindReferenceSummary`` or dict.
        mandatory_skeleton: Optional mandatory skeleton object (from template).
        checkpoint_titles: Optional list of checkpoint titles for routing hints.

    Returns:
        Parsed outline dict from the LLM response.
    """
    # Build routing hints when both reference and template are present
    routing_hints = ""
    if xmind_reference_summary and checkpoint_titles and mandatory_skeleton is not None:
        try:
            from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer

            analyzer = XMindReferenceAnalyzer()
            routing_hints = analyzer.generate_routing_hints(
                xmind_reference_summary, checkpoint_titles
            )
        except Exception:
            logger.warning(
                "Failed to generate routing hints; proceeding without them",
                exc_info=True,
            )

    xmind_section = _build_xmind_reference_prompt_section(
        xmind_reference_summary=xmind_reference_summary,
        has_mandatory_skeleton=mandatory_skeleton is not None,
        routing_hints=routing_hints,
    )

    user_message = f"""Please analyze the following document and generate a checkpoint outline.

Document Type: {doc_type}

Document Content:
{doc_content}
{xmind_section}
Please generate a structured checkpoint outline in JSON format."""

    response = call_llm(
        model=model,
        system_prompt=CHECKPOINT_OUTLINE_PLANNER_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3
    )

    result = extract_json_from_response(response)

    return result
