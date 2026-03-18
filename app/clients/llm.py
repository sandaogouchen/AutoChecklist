"""LLM 客户端模块。

提供与 OpenAI 兼容 API 交互的客户端抽象，包括：
- ``LLMClientConfig``：客户端配置数据类
- ``LLMClient``：基础 LLM 客户端，支持 chat / JSON 解析 / 结构化生成
- ``OpenAICompatibleLLMClient``：从配置对象构造的便捷子类
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar, get_origin

from openai import OpenAI
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMClientConfig:
    """LLM 客户端配置。"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    extra_params: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """OpenAI 兼容 API 的轻量封装。

    提供 ``chat()``、``parse_json_response()`` 和
    ``generate_structured()`` 三个核心方法。
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    # ------------------------------------------------------------------
    # 核心聊天方法
    # ------------------------------------------------------------------

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """发送聊天补全请求，返回助手消息文本。

        Args:
            system_prompt: 系统指令。
            user_prompt: 用户消息。
            temperature: 覆盖默认温度。
            max_tokens: 覆盖默认最大 token 数。

        Returns:
            助手回复的文本内容。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception:
            logger.exception("LLM 调用失败")
            raise

        content: str = response.choices[0].message.content or ""
        logger.debug("LLM 响应长度: %d 字符", len(content))
        return content

    # ------------------------------------------------------------------
    # JSON 解析辅助
    # ------------------------------------------------------------------

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any] | list:
        """从 LLM 响应文本中解析 JSON 对象或数组。

        兼容 LLM 常见的输出格式：纯 JSON、Markdown 代码围栏包裹的 JSON、
        以及带有额外文本的 JSON。同时接受顶层为 dict 或 list 的 JSON。

        Args:
            text: LLM 返回的原始文本。

        Returns:
            解析后的 dict 或 list。

        Raises:
            ValueError: 无法从文本中提取有效 JSON。
        """
        cleaned = text.strip()

        # 去除 Markdown 代码围栏
        fence_pattern = re.compile(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
        )
        match = fence_pattern.search(cleaned)
        if match:
            cleaned = match.group(1).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # 兜底：尝试提取第一个 { ... } 块
            brace_match = re.search(r"\{.*}", cleaned, re.DOTALL)
            if brace_match:
                try:
                    parsed = json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    raise ValueError(
                        f"无法从 LLM 响应中解析 JSON: {exc}"
                    ) from exc
            else:
                raise ValueError(
                    f"无法从 LLM 响应中解析 JSON: {exc}"
                ) from exc

        # 仅允许 dict 或 list，其余类型（int / str / None 等）视为非法
        if not isinstance(parsed, (dict, list)):
            raise ValueError(
                f"期望 JSON 对象 (dict) 或数组 (list)，"
                f"实际为 {type(parsed).__name__}"
            )
        return parsed

    # ------------------------------------------------------------------
    # 结构化生成
    # ------------------------------------------------------------------

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        model: Optional[str] = None,  # noqa: ARG002 — 保留以兼容调用方
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> T:
        """生成结构化（Pydantic 模型）响应。

        组合 :meth:`chat` + :meth:`parse_json_response` + Pydantic
        ``model_validate``，一次调用即可获得经过校验的模型实例。

        当 LLM 返回顶层 JSON 数组时，会自动尝试将其包装为 dict 再校验；
        若包装失败或校验失败，异常消息中会携带 LLM 原始输出前 2000 字符，
        方便在工作流日志中定位具体是哪个节点、LLM 返回了什么内容。

        Args:
            system_prompt: 系统指令（应引导 LLM 输出符合 response_model 的 JSON）。
            user_prompt: 用户上下文。
            response_model: 用于校验的 Pydantic BaseModel 子类。
            model: 忽略——构造时已固定模型。保留此参数以兼容调用方。
            temperature: 覆盖默认温度。
            max_tokens: 覆盖默认最大 token 数。

        Returns:
            经过校验的 response_model 实例。
        """
        model_name = response_model.__name__
        logger.info("generate_structured: 请求 %s", model_name)

        raw_text = self.chat(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.debug("generate_structured: 原始响应: %.500s", raw_text)

        try:
            parsed = self.parse_json_response(raw_text)
        except ValueError as exc:
            logger.exception(
                "generate_structured: 无法解析 LLM 响应中的 JSON"
            )
            raise ValueError(
                f"generate_structured({model_name}) 失败: {exc}\n"
                f"--- LLM 原始输出 (前2000字符) ---\n{raw_text[:2000]}"
            ) from exc

        # ------------------------------------------------------------------
        # list → dict 自动包装逻辑
        #
        # 当 LLM 直接返回一个 JSON 数组而非对象时，尝试自动包装为 dict，
        # 以便后续 Pydantic 校验能正常进行。具体策略：遍历 response_model
        # 的所有字段，找到类型注解为 list[...] 的字段；如果恰好有且仅有
        # 一个这样的字段，就将解析到的 list 包装为 {field_name: parsed_list}。
        # 若存在多个或零个 list 字段，则说明 LLM 输出格式不符合预期，
        # 直接抛出 ValueError 让调用方知晓。
        # ------------------------------------------------------------------
        if isinstance(parsed, list):
            list_fields: list[str] = []
            for field_name, field_info in response_model.model_fields.items():
                annotation = field_info.annotation
                if get_origin(annotation) is list:
                    list_fields.append(field_name)

            if len(list_fields) == 1:
                logger.debug(
                    "generate_structured: LLM 返回了顶层 list，"
                    "自动包装到字段 '%s'",
                    list_fields[0],
                )
                parsed_dict: dict[str, Any] = {list_fields[0]: parsed}
            else:
                raise ValueError(
                    f"generate_structured({model_name}) 失败: "
                    f"LLM 返回了 JSON 数组，但 {model_name} 中"
                    f"{'有多个' if len(list_fields) > 1 else '没有'} "
                    f"list 类型字段，无法自动包装\n"
                    f"--- LLM 原始输出 (前2000字符) ---\n{raw_text[:2000]}"
                )
        else:
            parsed_dict = parsed

        logger.debug(
            "generate_structured: 解析得到的 dict 键: %s",
            list(parsed_dict.keys()),
        )

        try:
            result = response_model.model_validate(parsed_dict)
        except ValidationError as exc:
            logger.exception(
                "generate_structured: Pydantic 校验失败 (%s)", model_name,
            )
            raise ValueError(
                f"generate_structured({model_name}) Pydantic 校验失败: {exc}\n"
                f"--- LLM 原始输出 (前2000字符) ---\n{raw_text[:2000]}"
            ) from exc

        logger.info(
            "generate_structured: 成功校验 %s", model_name,
        )
        return result


class OpenAICompatibleLLMClient(LLMClient):
    """从 :class:`LLMClientConfig` 构造的便捷 LLM 客户端子类。

    使调用方（如 ``workflow_service.py``）可以直接从配置对象创建客户端::

        config = LLMClientConfig(api_key="sk-...", model="gpt-4o")
        client = OpenAICompatibleLLMClient(config)
    """

    def __init__(self, config: LLMClientConfig) -> None:
        super().__init__(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
        )
        self.config = config
