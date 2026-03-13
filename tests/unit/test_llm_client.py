import pytest
from pydantic import BaseModel

from app.clients.llm import LLMClientConfig, OpenAICompatibleLLMClient


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

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.post_calls: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.post_calls.append((url, json))
        return _FakeResponse(self.__class__.next_content)


def _build_client(monkeypatch, *, base_url: str = "https://example.com/v1", content: str = '{"status":"ok"}') -> OpenAICompatibleLLMClient:
    _RecordingHttpxClient.instances.clear()
    _RecordingHttpxClient.next_content = content
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
