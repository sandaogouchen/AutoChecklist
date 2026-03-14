from __future__ import annotations

from app.clients.llm import LLMClient
from app.domain.research_models import ResearchOutput
from app.domain.state import GlobalState


def build_context_research_node(llm_client: LLMClient):
    def context_research_node(state: GlobalState) -> GlobalState:
        parsed_document = state["parsed_document"]
        response = llm_client.generate_structured(
            system_prompt=(
                "You extract testing-relevant product context from PRD documents. "
                "Return concise structured JSON. Include a `facts` array where each fact captures one "
                "verifiable change point from the PRD with `id`, `summary`, `change_type`, "
                "`requirement`, `branch_hint`, and structured `evidence_refs`."
            ),
            user_prompt=(
                f"Language: {state.get('language', 'zh-CN')}\n"
                f"Document title: {parsed_document.source.title if parsed_document.source else ''}\n"
                f"Document body:\n{parsed_document.raw_text}"
            ),
            response_model=ResearchOutput,
            model=state.get("model_config").model if state.get("model_config") else None,
        )
        return {"research_output": response}

    return context_research_node
