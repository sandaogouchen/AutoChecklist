from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.clients.llm import LLMClientConfig, OpenAICompatibleLLMClient
from app.domain.research_models import ResearchOutput
from app.nodes.draft_writer import DraftCaseCollection


class _StructuredResponse(BaseModel):
    status: str


class _FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class _FakeOpenAI:
    instances: list["_FakeOpenAI"] = []
    next_content = '{"status":"ok"}'

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.create_calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )
        self.__class__.instances.append(self)

    def _create(self, **kwargs):
        self.create_calls.append(kwargs)
        return _FakeOpenAIResponse(self.__class__.next_content)


class _FakeCocoClient:
    instances: list["_FakeCocoClient"] = []

    def __init__(self, settings, llm_client=None) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.send_task_calls: list[dict[str, object]] = []
        self.poll_task_calls: list[dict[str, object]] = []
        self.next_task_id = "task-coco-1"
        self.next_task = {
            "Id": "task-coco-1",
            "Status": "completed",
            "Messages": [
                {
                    "Role": "agent",
                    "Parts": [
                        {
                            "Text": {
                                "Text": '{"status":"ok"}',
                            }
                        }
                    ],
                }
            ],
        }
        self.__class__.instances.append(self)

    async def send_task(
        self,
        prompt: str,
        mr_url: str = "",
        git_url: str = "",
        agent_name: str | None = None,
    ) -> str:
        self.send_task_calls.append(
            {
                "prompt": prompt,
                "mr_url": mr_url,
                "git_url": git_url,
                "agent_name": agent_name,
            }
        )
        return self.next_task_id

    async def poll_task(
        self,
        task_id: str,
        timeout: int | None = None,
    ) -> dict[str, object]:
        self.poll_task_calls.append({"task_id": task_id, "timeout": timeout})
        return self.next_task

    @staticmethod
    def _get_assistant_text(task: dict[str, object]) -> str:
        return task["Messages"][0]["Parts"][0]["Text"]["Text"]


class _FakeMiraClient:
    instances: list["_FakeMiraClient"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.send_message_sync_calls: list[dict[str, object]] = []
        self.create_session_calls: list[dict[str, object]] = []
        self.delete_session_calls: list[str] = []
        self.next_response = SimpleNamespace(content='{"status":"ok"}')
        self.create_session_side_effects: list[object] = []
        self.send_message_sync_side_effects: list[object] = []
        self._session_counter = 0
        self.__class__.instances.append(self)

    def create_session(self, topic: str, model: str = "", data_sources=None) -> str:
        self.create_session_calls.append(
            {
                "topic": topic,
                "model": model,
                "data_sources": data_sources,
            }
        )
        if self.create_session_side_effects:
            effect = self.create_session_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return str(effect)

        self._session_counter += 1
        return f"mira-session-{self._session_counter}"

    def send_message_sync(
        self,
        session_id: str,
        content: str,
        config=None,
    ):
        self.send_message_sync_calls.append(
            {
                "session_id": session_id,
                "content": content,
                "config": config,
            }
        )
        if self.send_message_sync_side_effects:
            effect = self.send_message_sync_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return self.next_response

    def delete_session(self, session_id: str) -> bool:
        self.delete_session_calls.append(session_id)
        return True


def _build_openai_client(
    monkeypatch,
    *,
    base_url: str = "https://example.com/v1",
    content: str = '{"status":"ok"}',
    timeout_seconds: float = 60.0,
) -> OpenAICompatibleLLMClient:
    _FakeOpenAI.instances.clear()
    _FakeOpenAI.next_content = content
    monkeypatch.setattr("app.clients.llm.OpenAI", _FakeOpenAI)
    return OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="test-key",
            base_url=base_url,
            model="test-model",
            timeout_seconds=timeout_seconds,
        )
    )


def test_llm_client_builds_openai_sdk_with_config(monkeypatch) -> None:
    _build_openai_client(
        monkeypatch,
        base_url="https://example.com/v1",
        timeout_seconds=42.0,
    )

    openai_client = _FakeOpenAI.instances[0]

    assert openai_client.kwargs == {
        "api_key": "test-key",
        "base_url": "https://example.com/v1",
        "timeout": 42.0,
    }


def test_llm_client_sends_chat_completion_request(monkeypatch) -> None:
    client = _build_openai_client(monkeypatch)

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    call = _FakeOpenAI.instances[0].create_calls[0]
    assert call["model"] == "test-model"
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][0]["content"].startswith("system\n\n--- JSON Schema Constraint ---")
    assert call["messages"][1] == {"role": "user", "content": "user"}
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 4096
    assert call["response_format"] == {"type": "json_object"}


def test_llm_client_accepts_fenced_json_response(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='```json\n{"status":"ok"}\n```',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"


def test_llm_client_rejects_unexpected_wrapper_object_response(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='{"document":{"status":"ok"}}',
    )

    with pytest.raises(ValueError, match="Pydantic 校验失败"):
        client.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=_StructuredResponse,
        )


def test_llm_client_accepts_top_level_list_for_single_list_field_model(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='[{"id":"TC-001","title":"Login succeeds","steps":["Open login"],"expected_results":["Dashboard shown"],"evidence_refs":[]}]',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=DraftCaseCollection,
    )

    assert len(response.test_cases) == 1
    assert response.test_cases[0].id == "TC-001"


def test_llm_client_coerces_string_evidence_refs_into_objects(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='{"test_cases":[{"id":"TC-001","title":"Login succeeds","steps":["Open login"],"expected_results":["Dashboard shown"],"evidence_refs":["prd (1-105): Successful login redirects to the dashboard."]}]}',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=DraftCaseCollection,
    )

    assert len(response.test_cases[0].evidence_refs) == 1
    assert response.test_cases[0].evidence_refs[0].section_title == "prd"
    assert response.test_cases[0].evidence_refs[0].line_start == 1
    assert response.test_cases[0].evidence_refs[0].line_end == 105


def test_llm_client_coerces_research_evidence_refs_with_section_and_quote_keys(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='{"facts":[{"id":"F001","summary":"Optimize goal can be selected","evidence_refs":[{"section":"Ad group > optimize goal","quote":"Provide options 2 secondary goals [single selection]"}]}]}',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=ResearchOutput,
    )

    assert response.facts[0].fact_id == "F001"
    assert response.facts[0].description == "Optimize goal can be selected"
    assert response.facts[0].evidence_refs[0].section_title == "Ad group > optimize goal"
    assert response.facts[0].evidence_refs[0].excerpt == "Provide options 2 secondary goals [single selection]"


def test_llm_client_coerces_research_requirement_objects_into_strings(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content='{"facts":[{"id":"F001","summary":"Optimize goal can be selected","requirement":{"scope":"Ad group > optimize goal","detail":"Provide options 2 secondary goals [single selection]"},"evidence_refs":[]}]}',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=ResearchOutput,
    )

    assert response.facts[0].fact_id == "F001"
    assert response.facts[0].description == "Optimize goal can be selected"
    assert response.facts[0].requirement == "Ad group > optimize goal | Provide options 2 secondary goals [single selection]"


def test_llm_client_unwraps_stringified_result_payload(monkeypatch) -> None:
    client = _build_openai_client(
        monkeypatch,
        content=(
            '{"duration_api_ms":10,"duration_ms":12,"result":"{'
            '\\"test_cases\\":[{'
            '\\"id\\":\\"TC-001\\",'
            '\\"title\\":\\"Login succeeds\\",'
            '\\"steps\\":[\\"Open login\\"],'
            '\\"expected_results\\":[\\"Dashboard shown\\"],'
            '\\"evidence_refs\\":[]'
            '}]}"}'
        ),
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=DraftCaseCollection,
    )

    assert len(response.test_cases) == 1
    assert response.test_cases[0].id == "TC-001"


def test_llm_client_uses_coco_as_llm_when_enabled(monkeypatch) -> None:
    _FakeCocoClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.CocoClient", _FakeCocoClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="http://localhost:8317/v1",
            model="kimi-k2-250711",
            timeout_seconds=77.0,
            use_coco_as_llm=True,
            coco_api_base_url="https://codebase-api.byted.org/v2",
            coco_jwt_token="jwt-token",
            coco_agent_name="sandbox",
        )
    )

    response = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert len(_FakeCocoClient.instances) == 1
    coco_client = _FakeCocoClient.instances[0]
    assert coco_client.settings.coco_jwt_token == "jwt-token"
    assert coco_client.settings.coco_api_base_url == "https://codebase-api.byted.org/v2"
    assert coco_client.settings.coco_model_name == "kimi-k2-250711"
    send_call = coco_client.send_task_calls[0]
    assert send_call["prompt"].startswith(
        "You are strict JSON only.\n\n--- JSON Schema Constraint ---"
    )
    assert send_call["prompt"].endswith("Return the status payload.")
    assert send_call["mr_url"] == ""
    assert send_call["git_url"] == ""
    assert send_call["agent_name"] == "sandbox"
    assert coco_client.poll_task_calls == [{"task_id": "task-coco-1", "timeout": 77}]


def test_llm_client_requires_coco_jwt_token_when_coco_mode_enabled() -> None:
    with pytest.raises(ValueError, match="COCO_JWT_TOKEN"):
        OpenAICompatibleLLMClient(
            LLMClientConfig(
                api_key="",
                base_url="https://codebase-api.byted.org/v2",
                model="kimi-k2-250711",
                use_coco_as_llm=True,
            )
        )


def test_llm_client_uses_mira_as_llm_when_enabled(monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="https://unused.example/v1",
            model="mira-model",
            timeout_seconds=88.0,
            use_mira_as_llm=True,
            mira_api_base_url="https://mira.example.com",
            mira_jwt_token="mira-jwt",
        )
    )

    response = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert len(_FakeMiraClient.instances) == 1
    mira_client = _FakeMiraClient.instances[0]
    assert mira_client.config.base_url == "https://mira.example.com"
    assert mira_client.config.jwt_token == "mira-jwt"
    assert mira_client.create_session_calls == [
        {
            "topic": "autochecklist-llm",
            "model": "mira-model",
            "data_sources": [],
        }
    ]
    assert len(mira_client.send_message_sync_calls) == 1
    send_call = mira_client.send_message_sync_calls[0]
    assert send_call["session_id"] == "mira-session-1"
    assert send_call["config"] == {"model": "mira-model"}
    assert send_call["content"].startswith(
        "You are strict JSON only.\n\n--- JSON Schema Constraint ---"
    )
    assert '"status"' in send_call["content"]
    assert send_call["content"].endswith(
        "}\n```\n--- End of Schema ---\n\nReturn the status payload."
    )


def test_llm_client_requires_mira_jwt_token_when_mira_mode_enabled() -> None:
    with pytest.raises(ValueError, match="MIRA_JWT_TOKEN"):
        OpenAICompatibleLLMClient(
            LLMClientConfig(
                api_key="",
                base_url="https://unused.example/v1",
                model="mira-model",
                use_mira_as_llm=True,
                mira_api_base_url="https://mira.example.com",
            )
        )


def test_llm_client_allows_mira_cookie_without_jwt(monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="https://unused.example/v1",
            model="gpt-5.4",
            use_mira_as_llm=True,
            mira_api_base_url="https://mira.example.com",
            mira_cookie="locale=zh-CN; mira_session=session-token",
        )
    )

    response = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert len(_FakeMiraClient.instances) == 1
    assert _FakeMiraClient.instances[0].config.jwt_token == ""
    assert _FakeMiraClient.instances[0].config.session_cookie == (
        "locale=zh-CN; mira_session=session-token"
    )


def test_llm_client_retries_create_session_without_model_after_session_invalid(monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="https://unused.example/v1",
            model="mira-model",
            use_mira_as_llm=True,
            mira_api_base_url="https://mira.example.com",
            mira_jwt_token="mira-jwt",
        )
    )
    mira_client = _FakeMiraClient.instances[0]
    mira_client.create_session_side_effects = [
        ValueError("Mira create_session 失败: code=20001, msg=session invalid, log_id=log-1"),
        "mira-session-fallback",
    ]

    response = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert mira_client.create_session_calls == [
        {
            "topic": "autochecklist-llm",
            "model": "mira-model",
            "data_sources": [],
        },
        {
            "topic": "autochecklist-llm",
            "model": "",
            "data_sources": [],
        },
    ]
    assert mira_client.send_message_sync_calls == [
        {
            "session_id": "mira-session-fallback",
            "content": mira_client.send_message_sync_calls[0]["content"],
            "config": {"model": "mira-model"},
        }
    ]


def test_llm_client_recreates_mira_session_after_session_invalid_on_send(monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="https://unused.example/v1",
            model="mira-model",
            use_mira_as_llm=True,
            mira_api_base_url="https://mira.example.com",
            mira_jwt_token="mira-jwt",
        )
    )
    mira_client = _FakeMiraClient.instances[0]
    mira_client.send_message_sync_side_effects = [
        ValueError("Mira send_message 失败: code=20001, msg=session invalid, log_id=log-2"),
        SimpleNamespace(content='{"status":"ok"}'),
    ]

    response = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert mira_client.create_session_calls == [
        {
            "topic": "autochecklist-llm",
            "model": "mira-model",
            "data_sources": [],
        },
        {
            "topic": "autochecklist-llm",
            "model": "mira-model",
            "data_sources": [],
        },
    ]
    assert [call["session_id"] for call in mira_client.send_message_sync_calls] == [
        "mira-session-1",
        "mira-session-2",
    ]
    assert all(call["config"] == {"model": "mira-model"} for call in mira_client.send_message_sync_calls)


def test_llm_client_logs_mira_session_lifecycle(caplog, monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    with caplog.at_level(logging.INFO, logger="app.clients.llm"):
        client = OpenAICompatibleLLMClient(
            LLMClientConfig(
                api_key="",
                base_url="https://unused.example/v1",
                model="mira-model",
                timeout_seconds=42.0,
                use_mira_as_llm=True,
                mira_api_base_url="https://mira.example.com",
                mira_jwt_token="mira-jwt",
                timezone="UTC",
            )
        )
        response = client.generate_structured(
            system_prompt="You are strict JSON only.",
            user_prompt="Return the status payload.",
            response_model=_StructuredResponse,
        )

    assert response.status == "ok"
    assert "Mira LLM backend enabled" in caplog.text
    assert "timezone=UTC" in caplog.text
    assert "Mira session create requested" in caplog.text
    assert "Mira session created" in caplog.text
    assert "Mira message send started" in caplog.text
    assert "Mira message send completed" in caplog.text


def test_llm_client_creates_new_mira_session_for_each_request(monkeypatch) -> None:
    _FakeMiraClient.instances.clear()
    monkeypatch.setattr("app.clients.llm.MiraClient", _FakeMiraClient)

    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="",
            base_url="https://unused.example/v1",
            model="mira-model",
            use_mira_as_llm=True,
            mira_api_base_url="https://mira.example.com",
            mira_jwt_token="mira-jwt",
        )
    )

    response1 = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload.",
        response_model=_StructuredResponse,
    )
    response2 = client.generate_structured(
        system_prompt="You are strict JSON only.",
        user_prompt="Return the status payload again.",
        response_model=_StructuredResponse,
    )

    assert response1.status == "ok"
    assert response2.status == "ok"
    mira_client = _FakeMiraClient.instances[0]
    assert [call["topic"] for call in mira_client.create_session_calls] == [
        "autochecklist-llm",
        "autochecklist-llm",
    ]
    assert [call["session_id"] for call in mira_client.send_message_sync_calls] == [
        "mira-session-1",
        "mira-session-2",
    ]
    assert mira_client.delete_session_calls == [
        "mira-session-1",
        "mira-session-2",
    ]
