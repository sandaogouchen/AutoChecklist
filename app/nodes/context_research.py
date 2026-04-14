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
from app.services.prompt_loader import get_prompt_loader

_PROMPT_LOADER = get_prompt_loader()
_SYSTEM_PROMPT = _PROMPT_LOADER.load("nodes/context_research/system.md")


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
