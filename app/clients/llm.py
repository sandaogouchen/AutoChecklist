"""LLM 客户端模块。

提供与 OpenAI 兼容 API 进行结构化交互的能力：
- ``LLMClient``：协议接口，定义 LLM 调用的统一契约
- ``OpenAICompatibleLLMClient``：基于 httpx 的具体实现
- ``LLMClientConfig``：连接参数的数据模型
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, field_validator

# 泛型类型变量，约束为 Pydantic BaseModel 的子类，
# 用于 generate_structured() 的返回值类型推断
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class LLMClientConfig(BaseModel):
    """LLM 连接配置。

    ``api_key``、``base_url``、``model`` 三个必填字段会做非空校验，
    防止因配置缺失导致运行时才报错。
    """

    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 60.0
    temperature: float = 0.2
    max_tokens: int = 1600

    @field_validator("api_key", "base_url", "model")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """校验关键字段不能为空或纯空白字符串。"""
        if not value or not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class LLMClient(Protocol):
    """​LLM 客户端协议（接口）。

    任何实现了 ``generate_structured`` 方法的类均可作为 LLM 客户端注入，
    便于在测试中替换为 FakeLLMClient。
    """

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ResponseModelT:
        """向 LLM 发送请求并将 JSON 响应解析为类型安全的 Pydantic 模型。"""


class OpenAICompatibleLLMClient:
    """兼容 OpenAI Chat Completions API 的 LLM 客户端。

    通过 ``response_format: json_object`` 强制 LLM 返回 JSON，
    再利用 Pydantic ``model_validate_json`` 完成反序列化与校验。
    """

    def __init__(
        self,
        config: LLMClientConfig,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
        )

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ResponseModelT:
        """调用 LLM 并返回结构化结果。

        流程：构造请求 → 发送 HTTP POST → 提取返回文本 → Pydantic 反序列化。

        Raises:
            httpx.HTTPStatusError: 当 LLM API 返回非 2xx 状态码时。
            ValueError: 当响应格式不符合预期时。
            pydantic.ValidationError: 当 JSON 无法匹配目标模型时。
        """
        payload = self._build_request_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()

        content = _extract_message_content(response.json())
        return response_model.model_validate_json(content)

    def _build_request_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """构造符合 OpenAI Chat Completions API 规范的请求体。"""
        return {
            "model": model or self.config.model,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }


def _extract_message_content(payload: dict[str, Any]) -> str:
    """从 LLM 响应体中提取纯文本内容。

    兼容两种响应格式：
    1. ``content`` 为字符串（标准格式）
    2. ``content`` 为数组（多段 text 拼接格式）

    Raises:
        ValueError: 响应中缺少 choices 或无法提取文本内容。
    """
    choices = payload.get("choices")
    if not choices:
        raise ValueError("LLM response did not include choices")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # 标准格式：content 直接为字符串
    if isinstance(content, str):
        return content

    # 多段格式：content 为包含 type="text" 的对象数组
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_parts:
            return "".join(text_parts)

    raise ValueError("LLM response did not include structured text content")
