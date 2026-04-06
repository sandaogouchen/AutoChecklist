"""Coco 返回值三层容错校验器。

对 Coco Agent 返回的自然语言文本进行三层处理：
- Layer 1: JSON 提取与解析（正则匹配 ``\`\`\`json...\`\`\`` 或裸 ``{...}``）
- Layer 2: 逐字段 Schema 校验（Pydantic model_validate）
- Layer 3: LLM 推断填充（部分字段 / 全文推断 + 默认值兜底）

设计原则：任何单个字段校验失败都不应导致整体丢弃，
最终输出的数据模型必须 100% 符合内部 Schema。
"""
from __future__ import annotations

import json
import inspect
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class CocoResponseValidator:
    """Coco Agent 返回值校验器 + LLM 推断容错。

    Args:
        llm_client: LLM 客户端实例，需提供 ``chat(prompt: str) -> str`` 异步方法。
            传入 ``None`` 时跳过 LLM 推断层，直接使用默认值兜底。
        max_infer_retries: LLM 推断的最大重试次数，默认 2。
    """

    def __init__(self, llm_client: Any | None, max_infer_retries: int = 2):
        self._llm_client = llm_client
        self._max_infer_retries = max_infer_retries

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def _call_llm_chat(self, prompt: str) -> str:
        """兼容同步/异步 chat 接口与不同参数签名。"""
        chat_fn = self._llm_client.chat
        try:
            response = chat_fn(prompt)
        except TypeError:
            response = chat_fn(
                "你负责将 Coco 返回转换为严格 JSON。只输出 JSON。",
                prompt,
            )

        if inspect.isawaitable(response):
            return await response
        return response

    async def validate_and_fix(
        self,
        raw_text: str,
        schema_class: type[BaseModel],
        context: str = "",
    ) -> tuple[BaseModel, dict[str, Any]]:
        """对 Coco 返回的原始文本做三层容错处理。

        Args:
            raw_text: Coco Agent 返回的原始文本（可能包含 JSON 也可能是纯自然语言）。
            schema_class: 目标 Pydantic v2 模型类。
            context: 额外上下文信息（用于 LLM prompt 增强）。

        Returns:
            ``(validated_model, metadata)`` 元组。
            metadata 包含处理路径信息：
            - layer: ``"2-direct"`` / ``"3-partial"`` / ``"3-full"`` / ``"fallback-defaults"``
            - inferred_fields: 被 LLM 推断的字段名列表
            - raw_text_len: 原始文本长度
            - infer_attempt: LLM 推断重试次数
        """
        metadata: dict[str, Any] = {
            "layer": "none",
            "inferred_fields": [],
            "raw_text_len": len(raw_text),
        }

        # ---- Layer 1: JSON 提取 ----
        parsed = self._extract_json(raw_text)
        if parsed is None:
            logger.info("Layer 1 JSON 提取失败，进入 Layer 3-Full 推断")
            metadata["layer"] = "3-full"
            return await self._llm_full_infer(raw_text, schema_class, context, metadata)

        # ---- Layer 2: Schema 校验 ----
        try:
            model = schema_class.model_validate(parsed)
            metadata["layer"] = "2-direct"
            logger.debug("Layer 2 直接校验通过: %s", schema_class.__name__)
            return model, metadata
        except ValidationError as exc:
            failed_fields = self._extract_failed_fields(exc)
            metadata["failed_fields"] = failed_fields
            logger.info(
                "Layer 2 校验部分失败: %s, 失败字段=%s, 进入 Layer 3-Partial",
                schema_class.__name__,
                failed_fields,
            )

        # ---- Layer 3-Partial: 逐字段 LLM 推断 ----
        metadata["layer"] = "3-partial"
        return await self._llm_partial_infer(
            raw_text, parsed, failed_fields, schema_class, context, metadata
        )

    # ------------------------------------------------------------------
    # Layer 1: JSON 提取
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """从自然语言文本中提取 JSON 对象。

        按优先级尝试：
        1. 匹配 ``\`\`\`json ... \`\`\``` 代码块
        2. 匹配裸 ``{ ... }`` JSON 对象
        3. 尝试对整段文本直接 json.loads

        Returns:
            解析成功返回字典，失败返回 ``None``。
        """
        if not text or not text.strip():
            return None

        # 策略 1: ```json ... ```
        pattern_fenced = re.compile(
            r"```(?:json)?\s*\n?(\{[\s\S]*?\})\s*\n?```", re.DOTALL
        )
        match = pattern_fenced.search(text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略 2: 匹配最外层 { ... }（贪婪匹配最大的 JSON 块）
        brace_start = text.find("{")
        if brace_start != -1:
            # 从左大括号开始，寻找匹配的右大括号
            depth = 0
            in_string = False
            escape_next = False
            for i in range(brace_start, len(text)):
                ch = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\":
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[brace_start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break

        # 策略 3: 整段 json.loads
        try:
            result = json.loads(text.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        return None

    # ------------------------------------------------------------------
    # Layer 2 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_failed_fields(exc: ValidationError) -> list[str]:
        """从 ValidationError 中提取失败的顶层字段名。"""
        fields: list[str] = []
        for error in exc.errors():
            loc = error.get("loc", ())
            if loc:
                field_name = str(loc[0])
                if field_name not in fields:
                    fields.append(field_name)
        return fields

    # ------------------------------------------------------------------
    # Layer 3-Partial: 部分字段 LLM 推断
    # ------------------------------------------------------------------

    async def _llm_partial_infer(
        self,
        raw_text: str,
        parsed: dict[str, Any],
        failed_fields: list[str],
        schema_class: type[BaseModel],
        context: str,
        metadata: dict[str, Any],
    ) -> tuple[BaseModel, dict[str, Any]]:
        """对部分校验失败的字段进行 LLM 推断补全。"""
        if self._llm_client is None:
            logger.info("无 LLM 客户端，直接使用默认值兜底")
            metadata["layer"] = "fallback-defaults"
            metadata["inferred_fields"] = failed_fields
            return self._fill_defaults(parsed, schema_class), metadata

        schema_desc = schema_class.model_json_schema()

        # 构建已成功解析的字段摘要
        success_fields = {k: v for k, v in parsed.items() if k not in failed_fields}
        success_json = json.dumps(success_fields, ensure_ascii=False, default=str)[:2000]

        prompt = (
            "以下是 Coco Agent 返回的代码分析结果（原始文本）：\n"
            f"---\n{raw_text[:3000]}\n---\n\n"
            f"已成功解析的字段：{success_json}\n\n"
            f"以下字段校验失败，请根据原始文本推断并补全：\n"
            f"失败字段：{failed_fields}\n\n"
            f"目标 JSON Schema：\n{json.dumps(schema_desc, ensure_ascii=False)[:2000]}\n\n"
            f"上下文信息：{context[:500]}\n\n"
            "请仅输出一个完整的 JSON 对象，包含所有字段（含已成功字段 + 推断补全字段）。"
        )

        for attempt in range(self._max_infer_retries):
            try:
                llm_resp = await self._call_llm_chat(prompt)
                inferred = self._extract_json(llm_resp)
                if inferred:
                    try:
                        model = schema_class.model_validate(inferred)
                        metadata["inferred_fields"] = failed_fields
                        metadata["infer_attempt"] = attempt + 1
                        logger.info(
                            "Layer 3-Partial 推断成功: attempt=%d, fields=%s",
                            attempt + 1, failed_fields,
                        )
                        return model, metadata
                    except ValidationError as ve:
                        logger.debug(
                            "Layer 3-Partial 推断结果仍有错误 (attempt %d): %s",
                            attempt + 1, ve.error_count(),
                        )
            except Exception as exc:
                logger.warning("LLM 推断调用失败 (attempt %d): %s", attempt + 1, exc)

        # 所有重试失败 → 使用已解析字段 + 默认值
        logger.warning("Layer 3-Partial 推断全部失败，使用默认值兜底")
        metadata["layer"] = "fallback-defaults"
        metadata["inferred_fields"] = failed_fields
        return self._fill_defaults(parsed, schema_class), metadata

    # ------------------------------------------------------------------
    # Layer 3-Full: 全文 LLM 推断
    # ------------------------------------------------------------------

    async def _llm_full_infer(
        self,
        raw_text: str,
        schema_class: type[BaseModel],
        context: str,
        metadata: dict[str, Any],
    ) -> tuple[BaseModel, dict[str, Any]]:
        """JSON 完全提取失败时，整体交由 LLM 推断。"""
        if self._llm_client is None:
            logger.info("无 LLM 客户端，直接使用默认空模型兜底")
            metadata["layer"] = "fallback-defaults"
            return schema_class(), metadata

        schema_desc = schema_class.model_json_schema()
        prompt = (
            "以下是 Coco Agent 返回的原始文本，未能直接提取 JSON。\n"
            "请阅读全文，按目标 Schema 推断并输出合规 JSON。\n\n"
            f"--- 原始文本 ---\n{raw_text[:4000]}\n---\n\n"
            f"目标 JSON Schema：\n{json.dumps(schema_desc, ensure_ascii=False)[:2000]}\n\n"
            f"上下文：{context[:500]}\n\n"
            "请仅输出一个 JSON 对象。"
        )

        for attempt in range(self._max_infer_retries):
            try:
                llm_resp = await self._call_llm_chat(prompt)
                inferred = self._extract_json(llm_resp)
                if inferred:
                    try:
                        model = schema_class.model_validate(inferred)
                        metadata["infer_attempt"] = attempt + 1
                        logger.info(
                            "Layer 3-Full 推断成功: attempt=%d",
                            attempt + 1,
                        )
                        return model, metadata
                    except ValidationError as ve:
                        logger.debug(
                            "Layer 3-Full 推断结果校验失败 (attempt %d): %d errors",
                            attempt + 1, ve.error_count(),
                        )
            except Exception as exc:
                logger.warning("LLM 全文推断调用失败 (attempt %d): %s", attempt + 1, exc)

        # 最终兜底
        logger.warning("Layer 3-Full 推断全部失败，使用空模型兜底")
        metadata["layer"] = "fallback-defaults"
        return schema_class(), metadata

    # ------------------------------------------------------------------
    # Fallback: 默认值填充
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_defaults(parsed: dict[str, Any], schema_class: type[BaseModel]) -> BaseModel:
        """用已解析的合法字段 + Schema 默认值构造模型。

        对每个字段单独尝试赋值：能通过校验的保留，不能的使用默认值。
        """
        # 先尝试直接校验（可能部分字段已修正）
        try:
            return schema_class.model_validate(parsed)
        except ValidationError:
            pass

        # 逐字段尝试
        safe_fields: dict[str, Any] = {}
        schema_info = schema_class.model_json_schema()
        properties = schema_info.get("properties", {})

        for field_name in properties:
            if field_name in parsed:
                # 用单字段构造测试
                test_data = {field_name: parsed[field_name]}
                try:
                    # 尝试将该字段值赋给临时模型校验
                    partial = schema_class.model_construct(**test_data)
                    safe_fields[field_name] = parsed[field_name]
                except Exception:
                    pass

        try:
            return schema_class.model_validate(safe_fields)
        except ValidationError:
            return schema_class()
