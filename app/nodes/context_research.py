"""上下文研究节点。

调用 LLM 从 PRD 文档中提取与测试相关的结构化上下文信息，
包括功能主题、用户场景、约束条件、歧义点、测试信号和结构化事实。
"""

from __future__ import annotations

from app.clients.llm import LLMClient
from app.domain.research_models import ResearchOutput
from app.domain.state import GlobalState

# LLM 系统提示词：指导模型从 PRD 中提取测试相关上下文，包含结构化事实
_SYSTEM_PROMPT = (
    "You extract testing-relevant product context from PRD documents. "
    "In addition to feature_topics, user_scenarios, constraints, ambiguities, and test_signals, "
    "also extract a list of 'facts' — each fact is a discrete, testable piece of information "
    "from the PRD with a unique fact_id (e.g., FACT-001), description, source_section, "
    "category (requirement/constraint/assumption/behavior), and optional evidence_refs. "
    "For compatibility, facts may also include requirement and branch_hint, but requirement must be a string. "
    "evidence_refs must always be an array of objects using the exact shape "
    '{"section_title": string, "excerpt": string, "line_start": number, '
    '"line_end": number, "confidence": number}. '
    'Do not use alternate keys like "section" or "quote". '
    "Return concise structured JSON.\n\n"
    "【语言要求】\n"
    "- 所有通用描述、说明文字必须使用中文输出。\n"
    "- 英文专有名词必须保留原文，包括但不限于：产品名、品牌名、UI 按钮文案、"
    "字段名、枚举值、接口名、类名、函数名、变量名、ID、URL、配置项。\n"
    "- 中英文混排时采用「中文动作 + 原文对象」形式，例如：点击 `Create campaign`。\n"
    "- fact 的 description 字段使用中文描述，source_section 保留原文。"
)


def build_context_research_node(llm_client: LLMClient):
    """构建上下文研究节点的工厂函数。

    使用闭包捕获 ``llm_client``，返回符合 LangGraph 节点签名的可调用对象。

    Args:
        llm_client: LLM 客户端实例，用于发送结构化查询。
    """

    def context_research_node(state: GlobalState) -> GlobalState:
        """从 PRD 文档中提取测试上下文。

        将文档标题和正文拼接为 prompt 发送给 LLM，
        要求其返回符合 ``ResearchOutput`` 结构的 JSON，
        包含新增的 ``facts`` 字段。
        """
        parsed_document = state["parsed_document"]
        model_config = state.get("model_config")

        # ---- 项目上下文注入 ----
        project_context_summary = state.get("project_context_summary", "")
        project_prefix = ""
        if project_context_summary:
            project_prefix = f"[Project Context]\n{project_context_summary}\n\n"

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=(
                f"{project_prefix}"
                f"Language: {state.get('language', 'zh-CN')}\n"
                f"Document title: {parsed_document.source.title if parsed_document.source else ''}\n"
                f"Document body:\n{parsed_document.raw_text}"
            ),
            response_model=ResearchOutput,
            model=model_config.model if model_config else None,
        )
        return {"research_output": response}

    return context_research_node
