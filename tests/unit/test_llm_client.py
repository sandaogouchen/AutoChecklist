import httpx
import pytest
from pydantic import BaseModel

from app.clients.llm import LLMClientConfig, OpenAICompatibleLLMClient
from app.nodes.draft_writer import DraftCaseCollection


class _StructuredResponse(BaseModel):
    status: str


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": self._content}}]}


class _RecordingHttpxClient:
    instances: list["_RecordingHttpxClient"] = []
    next_content = '{"status":"ok"}'
    next_post_outcomes: list[object] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.post_calls: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.post_calls.append((url, json))
        if self.__class__.next_post_outcomes:
            outcome = self.__class__.next_post_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return _FakeResponse(self.__class__.next_content)


def _build_client(monkeypatch, *, base_url: str = "https://example.com/v1", content: str = '{"status":"ok"}') -> OpenAICompatibleLLMClient:
    _RecordingHttpxClient.instances.clear()
    _RecordingHttpxClient.next_content = content
    _RecordingHttpxClient.next_post_outcomes = []
    monkeypatch.setattr("app.clients.llm.httpx.Client", _RecordingHttpxClient)
    return OpenAICompatibleLLMClient(
        LLMClientConfig(
            api_key="test-key",
            base_url=base_url,
            model="test-model",
        )
    )


def test_llm_config_requires_api_key() -> None:
    with pytest.raises(ValueError):
        LLMClientConfig(
            api_key="",
            base_url="https://example.com/v1",
            model="test-model",
        )


@pytest.mark.parametrize(
    ("base_url", "expected_request_url"),
    [
        ("https://example.com/v1", "https://example.com/v1/chat/completions"),
        (
            "http://localhost:8317/v1/chat/completions/",
            "http://localhost:8317/v1/chat/completions",
        ),
    ],
)
def test_llm_client_uses_expected_chat_completions_url(monkeypatch, base_url: str, expected_request_url: str) -> None:
    client = _build_client(monkeypatch, base_url=base_url)

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert _RecordingHttpxClient.instances[0].post_calls[0][0] == expected_request_url


def test_llm_client_accepts_fenced_json_response(monkeypatch) -> None:
    client = _build_client(
        monkeypatch,
        content='```json\n{"status":"ok"}\n```',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"


def test_llm_client_accepts_single_wrapper_object_response(monkeypatch) -> None:
    client = _build_client(
        monkeypatch,
        content='{"document":{"status":"ok"}}',
    )

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"


def test_llm_client_accepts_top_level_list_for_single_list_field_model(monkeypatch) -> None:
    client = _build_client(
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
    client = _build_client(
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


def test_llm_client_retries_read_timeout_and_returns_success(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    _RecordingHttpxClient.next_post_outcomes = [
        httpx.ReadTimeout("timed out"),
        _FakeResponse('{"status":"ok"}'),
    ]

    response = client.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=_StructuredResponse,
    )

    assert response.status == "ok"
    assert len(_RecordingHttpxClient.instances[0].post_calls) == 2


def test_llm_client_raises_after_exhausting_read_timeout_retries(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    _RecordingHttpxClient.next_post_outcomes = [
        httpx.ReadTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
    ]

    with pytest.raises(httpx.ReadTimeout):
        client.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=_StructuredResponse,
        )

    assert len(_RecordingHttpxClient.instances[0].post_calls) == 3
