"""重试与降级机制的单元测试。

覆盖场景：
- 可重试错误（429/500/502/503/连接/超时）自动重试
- 不可重试错误（400/401/403）立即抛出
- 重试耗尽后触发 fallback 降级
- fallback 也失败时抛出错误
- max_retries=0 关闭重试
- 无 fallback 配置时重试耗尽直接抛出
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from pydantic import BaseModel

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient, _is_retryable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SimpleModel(BaseModel):
    status: str


def _make_chat_response(content: str = '{"status":"ok"}') -> ChatCompletion:
    """构造一个最小可用的 ChatCompletion 对象。"""
    return ChatCompletion(
        id="chatcmpl-test",
        created=0,
        model="test-model",
        object="chat.completion",
        choices=[
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content,
                ),
            )
        ],
    )


def _make_api_status_error(status_code: int, message: str = "error") -> APIStatusError:
    """构造一个 APIStatusError 实例。"""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.text = message
    mock_response.json.return_value = {"error": {"message": message}}
    return APIStatusError(
        message=message,
        response=mock_response,
        body={"error": {"message": message}},
    )


def _build_client(
    *,
    max_retries: int = 3,
    retry_base_delay: float = 0.0,  # 测试中禁用真实延迟
    retry_max_delay: float = 0.0,
    fallback_model: str = "",
    fallback_base_url: str = "",
    fallback_api_key: str = "",
) -> LLMClient:
    """构造一个用于测试的 LLMClient，Mock 掉 OpenAI 客户端。"""
    with patch("app.clients.llm.OpenAI") as mock_openai_cls:
        mock_primary = MagicMock()
        mock_fallback = MagicMock()

        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_primary
            return mock_fallback

        mock_openai_cls.side_effect = side_effect

        client = LLMClient(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="primary-model",
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
            fallback_model=fallback_model,
            fallback_base_url=fallback_base_url or "https://api.example.com/v1",
            fallback_api_key=fallback_api_key or "test-key",
        )

    client._mock_primary = mock_primary  # type: ignore[attr-defined]
    client._mock_fallback = mock_fallback  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# _is_retryable 单元测试
# ---------------------------------------------------------------------------

class TestIsRetryable:
    """测试 _is_retryable 错误分类函数。"""

    def test_api_connection_error_is_retryable(self) -> None:
        exc = APIConnectionError(request=MagicMock())
        assert _is_retryable(exc) is True

    def test_api_timeout_error_is_retryable(self) -> None:
        exc = APITimeoutError(request=MagicMock())
        assert _is_retryable(exc) is True

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_retryable_status_codes(self, status_code: int) -> None:
        exc = _make_api_status_error(status_code)
        assert _is_retryable(exc) is True

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_non_retryable_status_codes(self, status_code: int) -> None:
        exc = _make_api_status_error(status_code)
        assert _is_retryable(exc) is False

    def test_generic_exception_not_retryable(self) -> None:
        assert _is_retryable(ValueError("test")) is False

    def test_validation_error_not_retryable(self) -> None:
        assert _is_retryable(RuntimeError("validation failed")) is False


# ---------------------------------------------------------------------------
# 重试逻辑测试
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """测试 LLMClient.chat() 的重试行为。"""

    def test_success_on_first_attempt(self) -> None:
        """首次调用即成功，无重试。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.return_value = _make_chat_response()

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 1

    def test_chat_does_not_force_json_response_format(self) -> None:
        """普通 chat 默认不应强制要求 json_object。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.return_value = _make_chat_response("plain text")

        result = client.chat("system", "user")

        assert result == "plain text"
        kwargs = client._mock_primary.chat.completions.create.call_args.kwargs
        assert "response_format" not in kwargs

    def test_retry_on_429_then_success(self) -> None:
        """429 限流 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited"),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 2

    def test_retry_on_500_then_success(self) -> None:
        """500 服务端错误 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(500, "internal server error"),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 2

    def test_retry_on_502_then_success(self) -> None:
        """502 网关错误 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(502, "bad gateway"),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'

    def test_retry_on_503_then_success(self) -> None:
        """503 服务不可用 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(503, "service unavailable"),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'

    def test_retry_on_connection_error_then_success(self) -> None:
        """连接错误 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 2

    def test_retry_on_timeout_then_success(self) -> None:
        """超时错误 → 重试 → 成功。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 2

    def test_multiple_retries_then_success(self) -> None:
        """多次重试后最终成功。"""
        client = _build_client(max_retries=3)
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited 1"),
            _make_api_status_error(500, "server error 2"),
            _make_api_status_error(503, "server error 3"),
            _make_chat_response(),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert client._mock_primary.chat.completions.create.call_count == 4

    def test_retry_exhausted_returns_fallback_or_raises(self) -> None:
        """主模型重试耗尽。"""
        client = _build_client(max_retries=2)
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited 1"),
            _make_api_status_error(500, "server error 2"),
            _make_api_status_error(503, "server error 3"),
        ]

        with pytest.raises(APIStatusError):
            client.chat("system", "user")

        assert client._mock_primary.chat.completions.create.call_count == 3

    def test_sleep_called_between_retries(self) -> None:
        """重试期间会调用 sleep（但测试里 delay=0）。"""
        client = _build_client(max_retries=2, retry_base_delay=1.0, retry_max_delay=2.0)
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429),
            _make_api_status_error(500),
            _make_chat_response(),
        ]

        with patch.object(time, "sleep") as mock_sleep:
            result = client.chat("system", "user")

        assert result == '{"status":"ok"}'
        assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# 不可重试错误测试
# ---------------------------------------------------------------------------

class TestNonRetryableErrors:
    """测试不可重试错误是否立即抛出。"""

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_non_retryable_errors_raise_immediately(self, status_code: int) -> None:
        client = _build_client(max_retries=3)
        client._mock_primary.chat.completions.create.side_effect = _make_api_status_error(
            status_code,
            f"error {status_code}",
        )

        with pytest.raises(APIStatusError) as exc_info:
            client.chat("system", "user")

        assert exc_info.value.status_code == status_code
        # 不应重试
        assert client._mock_primary.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# fallback 降级逻辑测试
# ---------------------------------------------------------------------------

class TestFallbackLogic:
    """测试主模型失败后 fallback 模型是否生效。"""

    def test_fallback_success_after_primary_exhausted(self) -> None:
        """主模型重试耗尽后，fallback 成功。"""
        client = _build_client(max_retries=1, fallback_model="fallback-model")
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited"),
            _make_api_status_error(500, "server error"),
        ]
        client._mock_fallback.chat.completions.create.return_value = _make_chat_response(
            '{"status":"from-fallback"}'
        )

        result = client.chat("system", "user")

        assert result == '{"status":"from-fallback"}'
        assert client._mock_primary.chat.completions.create.call_count == 2
        assert client._mock_fallback.chat.completions.create.call_count == 1

    def test_fallback_also_retries(self) -> None:
        """fallback 模型同样享受重试保护。"""
        client = _build_client(max_retries=1, fallback_model="fallback-model")
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429),
            _make_api_status_error(500),
        ]
        client._mock_fallback.chat.completions.create.side_effect = [
            _make_api_status_error(503),
            _make_chat_response('{"status":"fallback-ok"}'),
        ]

        result = client.chat("system", "user")

        assert result == '{"status":"fallback-ok"}'
        assert client._mock_fallback.chat.completions.create.call_count == 2

    def test_primary_and_fallback_both_exhausted_raise_last_error(self) -> None:
        """主模型与 fallback 都重试耗尽，最终抛出 fallback 的最后错误。"""
        client = _build_client(max_retries=1, fallback_model="fallback-model")
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "primary rate limited"),
            _make_api_status_error(500, "primary server error"),
        ]
        client._mock_fallback.chat.completions.create.side_effect = [
            _make_api_status_error(503, "fallback unavailable"),
            _make_api_status_error(500, "fallback server error"),
        ]

        with pytest.raises(APIStatusError) as exc_info:
            client.chat("system", "user")

        # 最终应抛出 fallback 的最后错误
        assert exc_info.value.status_code == 500
        assert "fallback server error" in str(exc_info.value)

    def test_no_fallback_config_raises_primary_last_error(self) -> None:
        """未配置 fallback 时，主模型耗尽后直接抛错。"""
        client = _build_client(max_retries=1, fallback_model="")
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited"),
            _make_api_status_error(503, "unavailable"),
        ]

        with pytest.raises(APIStatusError) as exc_info:
            client.chat("system", "user")

        assert exc_info.value.status_code == 503
        assert client._mock_fallback.chat.completions.create.call_count == 0


# ---------------------------------------------------------------------------
# max_retries = 0 测试
# ---------------------------------------------------------------------------

class TestRetryDisabled:
    """测试 max_retries=0 时完全禁用重试。"""

    def test_no_retry_when_max_retries_zero(self) -> None:
        client = _build_client(max_retries=0)
        client._mock_primary.chat.completions.create.side_effect = _make_api_status_error(429)

        with pytest.raises(APIStatusError):
            client.chat("system", "user")

        assert client._mock_primary.chat.completions.create.call_count == 1

    def test_no_retry_but_fallback_still_works(self) -> None:
        """主模型不重试，但失败后仍可切到 fallback。"""
        client = _build_client(max_retries=0, fallback_model="fallback-model")
        client._mock_primary.chat.completions.create.side_effect = _make_api_status_error(429)
        client._mock_fallback.chat.completions.create.return_value = _make_chat_response(
            '{"status":"fallback-direct"}'
        )

        result = client.chat("system", "user")

        assert result == '{"status":"fallback-direct"}'
        assert client._mock_primary.chat.completions.create.call_count == 1
        assert client._mock_fallback.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# 配置透传测试
# ---------------------------------------------------------------------------

class TestConfigPassthrough:
    """测试 LLMClientConfig 是否正确透传到客户端。"""

    def test_retry_config_passthrough(self) -> None:
        """LLMClientConfig 的 retry 字段正确透传。"""
        config = LLMClientConfig(
            api_key="key",
            base_url="https://api.example.com/v1",
            model="primary",
            max_retries=5,
            retry_base_delay=2.0,
            retry_max_delay=120.0,
        )

        with patch("app.clients.llm.OpenAI"):
            client = OpenAICompatibleLLMClient(config)

        assert client._max_retries == 5
        assert client._retry_base_delay == 2.0
        assert client._retry_max_delay == 120.0

    def test_fallback_config_passthrough(self) -> None:
        """LLMClientConfig 的降级字段正确透传。"""
        config = LLMClientConfig(
            api_key="key",
            base_url="https://api.example.com/v1",
            model="primary",
            fallback_model="fallback",
            fallback_base_url="https://fallback.example.com/v1",
            fallback_api_key="fallback-key",
        )

        with patch("app.clients.llm.OpenAI"):
            client = OpenAICompatibleLLMClient(config)

        assert client._fallback_model == "fallback"
        assert client._fallback_client is not None

    def test_no_fallback_when_empty(self) -> None:
        """fallback_model 为空时不构造 fallback 客户端。"""
        config = LLMClientConfig(
            api_key="key",
            base_url="https://api.example.com/v1",
            model="primary",
            fallback_model="",
        )

        with patch("app.clients.llm.OpenAI"):
            client = OpenAICompatibleLLMClient(config)

        assert client._fallback_client is None


# ---------------------------------------------------------------------------
# generate_structured 集成测试（验证 retry 透传到 chat 层）
# ---------------------------------------------------------------------------

class TestGenerateStructuredWithRetry:
    """测试 generate_structured 是否正确继承 chat 层的重试行为。"""

    def test_generate_structured_retries_on_api_error(self) -> None:
        """generate_structured 通过 chat() 自动重试可恢复错误。"""
        client = _build_client(max_retries=1)
        client._mock_primary.chat.completions.create.side_effect = [
            _make_api_status_error(429, "rate limited"),
            _make_chat_response('{"status":"ok"}'),
        ]

        result = client.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=_SimpleModel,
        )

        assert result.status == "ok"
        assert client._mock_primary.chat.completions.create.call_count == 2

    def test_generate_structured_requests_json_response_format(self) -> None:
        """结构化生成仍应显式要求 json_object。"""
        client = _build_client()
        client._mock_primary.chat.completions.create.return_value = _make_chat_response('{"status":"ok"}')

        result = client.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=_SimpleModel,
        )

        assert result.status == "ok"
        kwargs = client._mock_primary.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}
