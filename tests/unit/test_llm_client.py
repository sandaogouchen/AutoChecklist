import pytest

from app.clients.llm import LLMClientConfig


def test_llm_config_requires_api_key() -> None:
    with pytest.raises(ValueError):
        LLMClientConfig(
            api_key="",
            base_url="https://example.com/v1",
            model="test-model",
        )
