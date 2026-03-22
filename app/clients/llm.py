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


def _build_schema_hint(response_model: Type[BaseModel]) -> str:
    """从 Pydantic model 提取 JSON Schema 摘要，作为 LLM 输出约束的一部分。

    将 response_model 的 JSON Schema 序列化为字符串，嵌入到 system prompt 中，
    以便 LLM 在生成响应时严格遵守字段定义和类型约束。

    Args:
        response_model: 用于校验 LLM 输出的 Pydantic BaseModel 子类。

    Returns:
        包含 JSON Schema 约束说明的字符串；若提取失败则返回空字符串。
    """
    try:
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        # 限制 schema 长度以避免过大的 prompt
        if len(schema_str) > 3000:
            schema_str = schema_str[:3000] + "\n... (schema truncated)"
        return (
            "\n\n--- JSON Schema Constraint ---\n"
            "Your response MUST conform to the following JSON Schema. "
            "Do NOT include any fields not defined in this schema.\n"
            f"```json\n{schema_str}\n```\n"
            "--- End of Schema ---"
        )
    except Exception:
        return ""


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
        model: Optional[str] = None,
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

        # 将 Pydantic schema 注入 system prompt，帮助 LLM 生成符合预期的 JSON
        schema_hint = _build_schema_hint(response_model)
        enriched_system_prompt = system_prompt + schema_hint

        raw_text = self.chat(
            enriched_system_prompt,
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

        # ---- 诊断日志：主列表字段为空时记录 LLM 原始响应 ----
        for _fname, _finfo in response_model.model_fields.items():
            if get_origin(_finfo.annotation) is list:
                _val = getattr(result, _fname, None)
                if _val is not None and len(_val) == 0:
                    logger.warning(
                        "generate_structured: %s.%s 为空列表，"
                        "LLM 原始响应前500字符: %.500s",
                        model_name, _fname, raw_text,
                    )
                break

        return result


class OpenAICompatibleLLMClient(LLMClient):
    """从 :class:`LLMClientConfig` 构造的便捷 LLM 客户端子类。"""

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
