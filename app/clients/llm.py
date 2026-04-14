"""LLM 客户端模块。

提供与 OpenAI 兼容 API 交互的客户端抽象，包括：
- ``LLMClientConfig``：客户端配置数据类
- ``LLMClient``：基础 LLM 客户端，支持 chat / JSON 解析 / 结构化生成
- ``OpenAICompatibleLLMClient``：从配置对象构造的便捷子类
"""

import asyncio
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from math import ceil
from types import SimpleNamespace
from typing import Any, Optional, Type, TypeVar, get_origin

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.clients.mira_client import MiraClient, MiraClientConfig
from app.services.coco_client import CocoClient

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


def _single_list_field_name(response_model: Type[BaseModel]) -> str | None:
    """返回模型中唯一的 list 字段名；否则返回 None。"""
    list_fields: list[str] = []
    for field_name, field_info in response_model.model_fields.items():
        if get_origin(field_info.annotation) is list:
            list_fields.append(field_name)
    if len(list_fields) == 1:
        return list_fields[0]
    return None


@dataclass
class LLMClientConfig:
    """LLM 客户端配置。"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    use_coco_as_llm: bool = False
    use_mira_as_llm: bool = False
    coco_api_base_url: str = ""
    coco_jwt_token: str = ""
    coco_agent_name: str = "sandbox"
    mira_api_base_url: str = ""
    mira_jwt_token: str = ""
    mira_cookie: str = ""
    mira_client_version: str = "autochecklist/0.1.0"
    mira_use_for_code_analysis: bool = False
    timezone: str = "Asia/Shanghai"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    extra_params: dict[str, Any] = field(default_factory=dict)


def _run_sync(coro: Any) -> Any:
    """在同步上下文中执行协程，兼容已有事件循环。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - 仅在线程桥接异常时触发
            error["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


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
        self.timeout_seconds = timeout_seconds
        self._use_coco_as_llm = False
        self._use_mira_as_llm = False
        self._coco_client: CocoClient | None = None
        self._mira_client: MiraClient | None = None
        self._coco_agent_name = "sandbox"

        if self._should_use_coco(api_key=api_key, base_url=base_url) and self._should_use_mira(
            api_key=api_key,
            base_url=base_url,
        ):
            raise ValueError("不能同时启用 Coco 和 Mira 作为 LLM 后端")

        if self._should_use_coco(api_key=api_key, base_url=base_url):
            self._use_coco_as_llm = True
            self._coco_agent_name = getattr(self, "_config_coco_agent_name", "sandbox")
            self._coco_client = self._build_coco_client(
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )
            self._client = None
            return

        if self._should_use_mira(api_key=api_key, base_url=base_url):
            self._use_mira_as_llm = True
            self._mira_client = self._build_mira_client(
                base_url=base_url,
                timeout_seconds=timeout_seconds,
            )
            logger.info(
                "Mira LLM backend enabled: model=%s timeout=%.1fs timezone=%s",
                model or "<default>",
                timeout_seconds,
                getattr(self, "_config_timezone", "Asia/Shanghai"),
            )
            self._client = None
            return

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    def _should_use_coco(self, api_key: str, base_url: str) -> bool:
        """由子类通过配置字段决定是否切换到 Coco 直连模式。"""
        del api_key, base_url
        return False

    def _should_use_mira(self, api_key: str, base_url: str) -> bool:
        """由子类通过配置字段决定是否切换到 Mira 模式。"""
        del api_key, base_url
        return False

    def _build_coco_client(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> CocoClient:
        """构造直接作为 LLM 使用的 Coco 客户端。"""
        coco_jwt_token = getattr(self, "_config_coco_jwt_token", "").strip()
        if not coco_jwt_token:
            raise ValueError("启用 Coco 作为 LLM 时必须配置 COCO_JWT_TOKEN")

        coco_base_url = getattr(self, "_config_coco_api_base_url", "").strip()
        if not coco_base_url:
            raise ValueError("启用 Coco 作为 LLM 时必须配置 COCO_API_BASE_URL")

        settings = SimpleNamespace(
            coco_api_base_url=coco_base_url,
            coco_jwt_token=coco_jwt_token,
            coco_agent_name=getattr(self, "_config_coco_agent_name", "sandbox"),
            coco_model_name=model,
            coco_task_timeout=max(1, int(ceil(timeout_seconds))),
            coco_poll_interval_start=2.0,
            coco_poll_interval_max=10.0,
        )
        return CocoClient(settings=settings)

    def _build_mira_client(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
    ) -> MiraClient:
        """构造 Mira 客户端。"""
        del base_url

        mira_jwt_token = getattr(self, "_config_mira_jwt_token", "").strip()
        mira_cookie = getattr(self, "_config_mira_cookie", "").strip()
        if not mira_jwt_token and not mira_cookie:
            raise ValueError("启用 Mira 作为 LLM 时必须配置 MIRA_JWT_TOKEN 或 MIRA_COOKIE")

        mira_base_url = getattr(self, "_config_mira_api_base_url", "").strip()
        if not mira_base_url:
            raise ValueError("启用 Mira 作为 LLM 时必须配置 MIRA_API_BASE_URL")

        config = MiraClientConfig(
            base_url=mira_base_url,
            jwt_token=mira_jwt_token,
            session_cookie=mira_cookie,
            default_model=self.model,
            timeout_seconds=timeout_seconds,
            timezone=getattr(self, "_config_timezone", "Asia/Shanghai"),
            client_version=getattr(
                self,
                "_config_mira_client_version",
                "autochecklist/0.1.0",
            ),
        )
        return MiraClient(config)

    def _create_mira_session(self, *, model: str) -> str:
        if self._mira_client is None:
            raise RuntimeError("Mira LLM 客户端未初始化")
        logger.info(
            "Mira session create requested: requested_model=%s",
            model or "<default>",
        )
        return self._mira_client.create_session(
            topic="autochecklist-llm",
            model=model,
            data_sources=[],
        )

    def _create_mira_session_for_request(self) -> str:
        """为单次请求创建独立的 Mira 会话。"""
        try:
            session_id = self._create_mira_session(model=self.model)
        except Exception as exc:
            if not self._is_mira_session_invalid_error(exc) or not self.model:
                raise
            logger.warning("Mira create_session 返回 session invalid，降级为不带 model 重试")
            session_id = self._create_mira_session(model="")
        logger.info("Mira session created: session_id=%s", session_id)
        return session_id

    def _safe_delete_mira_session(self, session_id: str) -> None:
        if self._mira_client is None or not session_id:
            return
        try:
            deleted = self._mira_client.delete_session(session_id)
            logger.info(
                "Mira session cleaned up: session_id=%s success=%s",
                session_id,
                deleted,
            )
        except Exception:
            logger.warning(
                "Mira session cleanup failed: session_id=%s",
                session_id,
                exc_info=True,
            )

    def _build_mira_message_config(self) -> dict[str, Any] | None:
        if not self.model:
            return None
        return {"model": self.model}

    @staticmethod
    def _is_mira_session_invalid_error(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code == 20001:
            return True

        message = str(exc).lower()
        return "session invalid" in message and "20001" in message

    def _send_mira_message_with_recovery(self, content: str) -> str:
        if self._mira_client is None:
            raise RuntimeError("Mira LLM 客户端未初始化")

        config = self._build_mira_message_config()
        session_id = self._create_mira_session_for_request()
        try:
            logger.info(
                "Mira message send started: session_id=%s content_len=%d config_keys=%s",
                session_id,
                len(content),
                sorted(config.keys()) if config else [],
            )
            try:
                response = self._mira_client.send_message_sync(
                    session_id=session_id,
                    content=content,
                    config=config,
                )
            except Exception as exc:
                if not self._is_mira_session_invalid_error(exc):
                    raise

                logger.warning("Mira 会话失效，重建独立会话后重试一次")
                self._safe_delete_mira_session(session_id)
                session_id = self._create_mira_session_for_request()
                response = self._mira_client.send_message_sync(
                    session_id=session_id,
                    content=content,
                    config=config,
                )

            logger.info(
                "Mira message send completed: session_id=%s response_len=%d",
                session_id,
                len(response.content),
            )
            return response.content
        finally:
            self._safe_delete_mira_session(session_id)

    @staticmethod
    def _merge_prompts(system_prompt: str, user_prompt: str) -> str:
        parts = []
        if system_prompt.strip():
            parts.append(system_prompt.strip())
        if user_prompt.strip():
            parts.append(user_prompt.strip())
        return "\n\n".join(parts)

    def _repair_structured_output(
        self,
        raw_text: str,
        response_model: Type[BaseModel],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """对非结构化输出做一次 JSON 重整回退。"""
        repair_system_prompt = (
            "The previous response did not follow the required JSON format. "
            "Rewrite it strictly into valid JSON only. "
            "Do not add markdown, comments, explanation, or any extra text."
            + _build_schema_hint(response_model)
        )
        repair_user_prompt = (
            "Rewrite the following response as JSON that matches the schema exactly.\n\n"
            "Original response:\n"
            "```text\n"
            f"{raw_text[:12000]}\n"
            "```"
        )
        return self.chat(
            repair_system_prompt,
            repair_user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _normalize_parsed_payload(
        parsed: dict[str, Any] | list,
        response_model: Type[BaseModel],
    ) -> dict[str, Any]:
        """归一化解析后的 JSON 载荷，兼容单列表模型的常见变体。"""
        parsed = LLMClient._unwrap_embedded_json_payload(parsed, response_model)
        list_field_name = _single_list_field_name(response_model)

        if isinstance(parsed, list):
            if list_field_name:
                logger.debug(
                    "generate_structured: LLM 返回了顶层 list，自动包装到字段 '%s'",
                    list_field_name,
                )
                return {list_field_name: parsed}
            raise ValueError(
                f"generate_structured({response_model.__name__}) 失败: "
                f"LLM 返回了 JSON 数组，但 {response_model.__name__} 中没有唯一的 list 类型字段可包装"
            )

        if list_field_name:
            field_names = set(response_model.model_fields.keys())
            if list_field_name not in parsed:
                list_valued_keys = [
                    key for key, value in parsed.items() if isinstance(value, list)
                ]
                if len(list_valued_keys) == 1 and list_valued_keys[0] not in field_names:
                    logger.debug(
                        "generate_structured: 将单列表字段别名 '%s' 归一化为 '%s'",
                        list_valued_keys[0],
                        list_field_name,
                    )
                    return {list_field_name: parsed[list_valued_keys[0]]}

        return parsed

    @staticmethod
    def _unwrap_embedded_json_payload(
        parsed: dict[str, Any] | list,
        response_model: Type[BaseModel],
    ) -> dict[str, Any] | list:
        """解包包装在 ``result`` / ``content`` 等字段中的 JSON 载荷。"""
        if not isinstance(parsed, dict):
            return parsed

        field_names = set(response_model.model_fields.keys())
        if field_names.intersection(parsed.keys()):
            return parsed

        for key in (
            "result",
            "content",
            "text",
            "answer",
            "outputText",
            "output_text",
            "finalContent",
            "value",
        ):
            if key not in parsed:
                continue

            candidate = parsed[key]
            if isinstance(candidate, (dict, list)):
                logger.debug(
                    "generate_structured: 解包嵌套 JSON 载荷，来源字段 '%s'",
                    key,
                )
                return candidate

            if not isinstance(candidate, str) or not candidate.strip():
                continue

            try:
                nested = LLMClient.parse_json_response(candidate)
            except ValueError:
                continue

            logger.debug(
                "generate_structured: 解包字符串化 JSON 载荷，来源字段 '%s'",
                key,
            )
            return nested

        return parsed

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
        if self._use_coco_as_llm:
            if self._coco_client is None:
                raise RuntimeError("Coco LLM 客户端未初始化")
            task_id = _run_sync(
                self._coco_client.send_task(
                    prompt=self._merge_prompts(system_prompt, user_prompt),
                    agent_name=self._coco_agent_name,
                )
            )
            task = _run_sync(
                self._coco_client.poll_task(
                    task_id,
                    timeout=max(1, int(ceil(self.timeout_seconds))),
                )
            )
            content = self._coco_client._get_assistant_text(task)
            logger.debug("Coco LLM 响应长度: %d 字符", len(content))
            return content

        if self._use_mira_as_llm:
            return self._send_mira_message_with_recovery(
                self._merge_prompts(system_prompt, user_prompt)
            )

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
            logger.warning(
                "generate_structured: 首次解析 JSON 失败，尝试结构化修复 (%s)",
                model_name,
            )
            repaired_text = self._repair_structured_output(
                raw_text,
                response_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.debug("generate_structured: 修复后响应: %.500s", repaired_text)
            try:
                parsed = self.parse_json_response(repaired_text)
                raw_text = repaired_text
            except ValueError:
                logger.exception(
                    "generate_structured: 修复后仍无法解析 LLM 响应中的 JSON"
                )
                raise ValueError(
                    f"generate_structured({model_name}) 失败: {exc}\n"
                    f"--- LLM 原始输出 (前2000字符) ---\n{raw_text[:2000]}"
                ) from exc

        parsed_dict = self._normalize_parsed_payload(parsed, response_model)

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
        self._config_use_coco_as_llm = config.use_coco_as_llm
        self._config_use_mira_as_llm = config.use_mira_as_llm
        self._config_coco_api_base_url = config.coco_api_base_url
        self._config_coco_jwt_token = config.coco_jwt_token
        self._config_coco_agent_name = config.coco_agent_name
        self._config_mira_api_base_url = config.mira_api_base_url
        self._config_mira_jwt_token = config.mira_jwt_token
        self._config_mira_cookie = config.mira_cookie
        self._config_mira_client_version = config.mira_client_version
        self._config_timezone = config.timezone
        super().__init__(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
        )
        self.config = config

    def _should_use_coco(self, api_key: str, base_url: str) -> bool:
        del api_key, base_url
        return bool(self._config_use_coco_as_llm)

    def _should_use_mira(self, api_key: str, base_url: str) -> bool:
        del api_key, base_url
        return bool(self._config_use_mira_as_llm)
