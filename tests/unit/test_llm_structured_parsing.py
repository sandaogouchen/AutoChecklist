from app.clients.llm import LLMClient
from app.domain.checklist_models import CanonicalOutlineNodeCollection
from app.nodes.draft_writer import DraftCaseCollection


class _StubLLMClient(LLMClient):
    def __init__(self, content: str) -> None:
        self._content = content

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature=None,
        max_tokens=None,
    ) -> str:
        return self._content


class _SequentialStubLLMClient(LLMClient):
    def __init__(self, contents: list[str]) -> None:
        self._contents = contents
        self.calls: list[dict[str, str]] = []

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature=None,
        max_tokens=None,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return self._contents.pop(0)


def test_generate_structured_accepts_testcases_key_for_single_list_field_model() -> None:
    client = _StubLLMClient(
        '{"testcases":[{"id":"TC-001","title":"登录成功","steps":["打开登录页"],'
        '"expected_results":["进入首页"],"evidence_refs":[]}]}'
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=DraftCaseCollection,
    )

    assert len(response.test_cases) == 1
    assert response.test_cases[0].id == "TC-001"


def test_generate_structured_repairs_non_json_text_with_followup_call() -> None:
    client = _SequentialStubLLMClient(
        [
            "大纲层级结构已构建完成。以下是关键设计说明：\n- Campaign\n- Ad Group",
            '{"canonical_nodes":[{"node_id":"node-campaign","semantic_key":"campaign","display_text":"Campaign","kind":"business_object","visibility":"visible","aliases":["campaign"]}]}',
        ]
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=CanonicalOutlineNodeCollection,
    )

    assert len(response.canonical_nodes) == 1
    assert response.canonical_nodes[0].node_id == "node-campaign"
    assert len(client.calls) == 2
    assert "Rewrite it strictly into valid JSON only" in client.calls[1]["system_prompt"]
    assert "大纲层级结构已构建完成" in client.calls[1]["user_prompt"]
