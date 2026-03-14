from __future__ import annotations

import json
import re
from typing import Any, Protocol, TypeVar, get_origin

import httpx
from pydantic import BaseModel, ValidationError, field_validator

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
CHAT_COMPLETIONS_PATH = "chat/completions"
FENCED_JSON_PATTERN = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
COMMON_WRAPPER_KEYS = ("data", "result", "output", "response", "research_output", "document")
READ_TIMEOUT_RETRY_ATTEMPTS = 2


class LLMClientConfig(BaseModel):
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 60.0
    temperature: float = 0.2
    max_tokens: int = 1600

    @field_validator("api_key", "base_url", "model")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class LLMClient(Protocol):
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
        """Generate a typed response from the backing LLM."""


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        config: LLMClientConfig,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._chat_completions_url = _resolve_chat_completions_url(config.base_url)
        self._client = client or httpx.Client(
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
        payload = {
            "model": model or self.config.model,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = self._post_with_read_timeout_retries(payload)
        response.raise_for_status()

        response_payload = response.json()
        content = _extract_message_content(response_payload)
        return _parse_structured_response(content, response_model)

    def _post_with_read_timeout_retries(self, payload: dict[str, Any]) -> httpx.Response:
        for attempt in range(READ_TIMEOUT_RETRY_ATTEMPTS + 1):
            try:
                return self._client.post(self._chat_completions_url, json=payload)
            except httpx.ReadTimeout:
                if attempt == READ_TIMEOUT_RETRY_ATTEMPTS:
                    raise

        raise RuntimeError("unreachable")


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("LLM response did not include choices")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_parts:
            return "".join(text_parts)

    raise ValueError("LLM response did not include structured text content")


def _parse_structured_response(content: str, response_model: type[ResponseModelT]) -> ResponseModelT:
    normalized_content = _normalize_json_content(content)
    try:
        return response_model.model_validate_json(normalized_content)
    except ValidationError as original_error:
        payload = json.loads(normalized_content)
        unwrapped_payload = _unwrap_common_wrapper(payload)
        if unwrapped_payload is not payload:
            return response_model.model_validate(unwrapped_payload)

        wrapped_payload = _wrap_top_level_list_for_single_list_field_model(payload, response_model)
        if wrapped_payload is payload:
            raise original_error
        return response_model.model_validate(wrapped_payload)


def _normalize_json_content(content: str) -> str:
    stripped_content = content.strip()
    fenced_match = FENCED_JSON_PATTERN.match(stripped_content)
    if fenced_match:
        return fenced_match.group(1).strip()
    return stripped_content


def _unwrap_common_wrapper(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    for key in COMMON_WRAPPER_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    if len(payload) == 1:
        only_value = next(iter(payload.values()))
        if isinstance(only_value, dict):
            return only_value

    return payload


def _wrap_top_level_list_for_single_list_field_model(
    payload: Any,
    response_model: type[ResponseModelT],
) -> Any:
    if not isinstance(payload, list):
        return payload

    model_fields = response_model.model_fields
    if len(model_fields) != 1:
        return payload

    field_name, field_info = next(iter(model_fields.items()))
    if get_origin(field_info.annotation) is not list:
        return payload

    return {field_name: payload}


def _resolve_chat_completions_url(base_url: str) -> str:
    normalized_base_url = base_url.strip().rstrip("/")
    if normalized_base_url.endswith(f"/{CHAT_COMPLETIONS_PATH}"):
        return normalized_base_url
    return f"{normalized_base_url}/{CHAT_COMPLETIONS_PATH}"
