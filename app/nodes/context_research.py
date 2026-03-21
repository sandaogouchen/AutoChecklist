"""上下文研究节点。

调用 LLM 从 PRD 文档中提取与测试相关的结构化上下文信息，
包括功能主题、用户场景、约束条件、歧义点、测试信号和结构化事实。

当知识检索结果（knowledge_context）可用时，将其作为额外的
「领域知识参考」注入 prompt，使 LLM 能够交叉分析 PRD 与知识库内容。
"""

from __future__ import annotations

from app.clients.llm import LLMClient
from app.domain.research_models import ResearchOutput
from app.domain.state import GlobalState

# LLM 系统提示词：指导模型从 PRD 中提取测试相关上下文，包含结构化事实
_SYSTEM_PROMPT = (
    "You extract testing-relevant product context from PRD documents. "
    "In addition to feature_topics, user_scenarios, constraints, ambiguities, and test_signals, "
    "also extract a list of 'facts' \u2014 each fact is a discrete, testable piece of information "
    "from the PRD with a unique fact_id (e.g., FACT-001), description, source_section, "
    "category (requirement/constraint/assumption/behavior), and optional evidence_refs. "
    "For compatibility, facts may also include requirement and branch_hint, but requirement must be a string. "
    "evidence_refs must always be an array of objects using the exact shape "
    '{"section_title": string, "excerpt": string, "line_start": number, '
    '"line_end": number, "confidence": number}. '
    'Do not use alternate keys like "section" or "quote". '
    "Return concise structured JSON.\n\n"
    "\u3010\u8bed\u8a00\u8981\u6c42\u3011\n"
    "- \u6240\u6709\u901a\u7528\u63cf\u8ff0\u3001\u8bf4\u660e\u6587\u5b57\u5fc5\u987b\u4f7f\u7528\u4e2d\u6587\u8f93\u51fa\u3002\n"
    "- \u82f1\u6587\u4e13\u6709\u540d\u8bcd\u5fc5\u987b\u4fdd\u7559\u539f\u6587\uff0c\u5305\u62ec\u4f46\u4e0d\u9650\u4e8e\uff1a\u4ea7\u54c1\u540d\u3001\u54c1\u724c\u540d\u3001UI \u6309\u94ae\u6587\u6848\u3001"
    "\u5b57\u6bb5\u540d\u3001\u679a\u4e3e\u503c\u3001\u63a5\u53e3\u540d\u3001\u7c7b\u540d\u3001\u51fd\u6570\u540d\u3001\u53d8\u91cf\u540d\u3001ID\u3001URL\u3001\u914d\u7f6e\u9879\u3002\n"
    "- \u4e2d\u82f1\u6587\u6df7\u6392\u65f6\u91c7\u7528\u300c\u4e2d\u6587\u52a8\u4f5c + \u539f\u6587\u5bf9\u8c61\u300d\u5f62\u5f0f\uff0c\u4f8b\u5982\uff1a\u70b9\u51fb `Create campaign`\u3002\n"
    "- fact \u7684 description \u5b57\u6bb5\u4f7f\u7528\u4e2d\u6587\u63cf\u8ff0\uff0csource_section \u4fdd\u7559\u539f\u6587\u3002"
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

        当 knowledge_context 可用时，将其作为「领域知识参考」
        段落注入 prompt，使 LLM 综合分析 PRD 与业务知识。
        """
        parsed_document = state["parsed_document"]
        model_config = state.get("model_config")

        # ---- 项目上下文注入 ----
        project_context_summary = state.get("project_context_summary", "")
        project_prefix = ""
        if project_context_summary:
            project_prefix = f"[Project Context]\n{project_context_summary}\n\n"

        # ---- 知识检索结果注入 ----
        knowledge_context = state.get("knowledge_context", "")
        knowledge_prefix = ""
        if knowledge_context:
            knowledge_prefix = (
                "[Domain Knowledge Reference]\n"
                "以下是从业务知识库中检索到的与本 PRD 相关的领域知识。"
                "请结合这些知识与 PRD 内容进行交叉分析，"
                "识别 PRD 未覆盖但知识库中提及的测试场景和边界条件。\n\n"
                f"{knowledge_context}\n\n"
            )

        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=(
                f"{project_prefix}"
                f"{knowledge_prefix}"
                f"Language: {state.get('language', 'zh-CN')}\n"
                f"Document title: {parsed_document.source.title if parsed_document.source else ''}\n"
                f"Document body:\n{parsed_document.raw_text}"
            ),
            response_model=ResearchOutput,
            model=model_config.model if model_config else None,
        )
        return {"research_output": response}

    return context_research_node