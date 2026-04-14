"""Mira API 客户端封装。"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


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
        except BaseException as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


@dataclass
class MiraClientConfig:
    """Mira 客户端配置。"""

    base_url: str
    jwt_token: str
    session_cookie: str = ""
    default_model: str = ""
    timezone: str = "Asia/Shanghai"
    timeout_seconds: float = 300.0
    max_retries: int = 3
    client_version: str = "autochecklist/0.1.0"


@dataclass
class MiraMessageResponse:
    """Mira 消息响应。"""

    message_id: str = ""
    content: str = ""
    content_type: str = "text"
    round_index: int = 0
    tasks: list[dict[str, Any]] = field(default_factory=list)
    raw_extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MiraFileInfo:
    """Mira 上传文件信息。"""

    file_name: str = ""
    url: str = ""
    uri: str = ""
    mime_type: str = ""
    is_sensitive: bool = False


@dataclass
class MiraModelMetadata:
    """Mira 模型元数据。"""

    model: str = ""
    display_name: str = ""
    raw_extra: dict[str, Any] = field(default_factory=dict)


class MiraClient:
    """Mira HTTP 客户端。"""

    _MESSAGE_POLL_ATTEMPTS = 3
    _MESSAGE_POLL_INTERVAL_SECONDS = 1.0

    def __init__(self, config: MiraClientConfig) -> None:
        self._config = config
        self._timeout = httpx.Timeout(config.timeout_seconds)
        self._cached_default_data_sources: list[dict[str, Any]] | None = None

    def _build_cookie_header_value(self) -> str:
        if self._config.session_cookie:
            return self._config.session_cookie
        if self._config.jwt_token:
            token = self._config.jwt_token.strip()
            if token.startswith("mira_session=") or ";" in token:
                return token
            return f"mira_session={token}"
        return ""

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "x-mira-client": self._config.client_version,
            "x-mira-timezone": self._config.timezone,
        }
        cookie_header = self._build_cookie_header_value()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    @property
    def config(self) -> MiraClientConfig:
        return self._config

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    def _find_first_string(
        self,
        payload: Any,
        candidate_keys: tuple[str, ...],
    ) -> str:
        """递归查找第一个匹配 key 的字符串值。"""
        if isinstance(payload, dict):
            for key in candidate_keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                found = self._find_first_string(value, candidate_keys)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_string(item, candidate_keys)
                if found:
                    return found
        return ""

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._config.base_url.rstrip('/')}{path}"
        headers = {**self._headers, **kwargs.pop("headers", {})}
        response = httpx.request(
            method,
            url,
            headers=headers,
            timeout=self._timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def _extract_biz_error(self, payload: Any) -> tuple[int | None, str, str]:
        """提取 Mira 自定义业务错误。"""
        if not isinstance(payload, dict):
            return None, "", ""
        code = payload.get("code")
        msg = payload.get("msg", "")
        log_id = payload.get("log_id", "")
        if isinstance(code, int) and code != 0:
            return code, str(msg), str(log_id)
        return None, "", ""

    def _load_default_data_sources(self) -> list[dict[str, Any]]:
        if self._cached_default_data_sources is not None:
            return [dict(item) for item in self._cached_default_data_sources]

        response = self._request("GET", "/global_config/web_configs")
        payload = self._normalize_payload(response.json())
        raw_sources = payload.get("dataSources", []) if isinstance(payload, dict) else []

        sources: list[dict[str, Any]] = []
        if isinstance(raw_sources, list):
            for item in raw_sources:
                if not isinstance(item, dict) or item.get("enable") is False:
                    continue
                key = str(item.get("key", "")).strip()
                if key:
                    sources.append({"key": key})

        self._cached_default_data_sources = [dict(item) for item in sources]
        return [dict(item) for item in sources]

    def _resolve_data_sources(
        self,
        data_sources: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if data_sources:
            return [dict(item) for item in data_sources if isinstance(item, dict)]
        return self._load_default_data_sources()

    def _get_role_context(self) -> dict[str, Any]:
        response = self._request("GET", "/devops/get_role")
        payload = self._normalize_payload(response.json())
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _has_role_context(role_context: dict[str, Any]) -> bool:
        for key in ("employeeNumber", "name", "email", "userId", "openId"):
            value = role_context.get(key)
            if isinstance(value, str) and value.strip():
                return True
        return False

    @staticmethod
    def _describe_create_session_payload(payload: dict[str, Any]) -> str:
        body = payload.get("sessionProperties", payload)
        prefix = "wrapped" if "sessionProperties" in payload else "flat"
        if not isinstance(body, dict):
            return f"{prefix}_unknown"

        if "dataSource" in body:
            return f"{prefix}_with_datasource"
        if "dataSources" in body:
            return f"{prefix}_with_datasources"
        return f"{prefix}_minimal"

    def _build_create_session_payload_variants(
        self,
        topic: str,
        model: str,
        data_sources: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        sources = [dict(item) for item in (data_sources or [])]
        default_source = dict(sources[0]) if sources else {}
        variants: list[dict[str, Any]] = []

        wrapped_variants = [
            {
                "topic": topic,
                "dataSource": default_source,
                "dataSources": sources,
            },
            {
                "topic": topic,
                "dataSources": sources,
            },
            {
                "topic": topic,
            },
        ]
        flat_variants = [
            {
                "topic": topic,
                "dataSource": default_source,
                "dataSources": sources,
            },
            {
                "topic": topic,
                "dataSources": sources,
            },
            {
                "topic": topic,
            },
        ]

        if model:
            for variant in wrapped_variants:
                variant["model"] = model
            for variant in flat_variants:
                variant["model"] = model

        for variant in wrapped_variants:
            variants.append({"sessionProperties": variant})
        variants.extend(flat_variants)
        return variants

    def create_session(
        self,
        topic: str,
        model: str = "",
        data_sources: list[dict[str, Any]] | None = None,
    ) -> str:
        resolved_data_sources = self._resolve_data_sources(data_sources)
        last_error = ""
        last_top_keys: list[str] = []
        saw_session_invalid = False

        for attempt, payload in enumerate(
            self._build_create_session_payload_variants(
                topic=topic,
                model=model,
                data_sources=resolved_data_sources,
            ),
            start=1,
        ):
            variant_name = self._describe_create_session_payload(payload)
            logger.info(
                "Mira create_session attempt=%d variant=%s topic=%s model=%s data_sources=%d",
                attempt,
                    variant_name,
                    topic,
                    model or "<default>",
                    len(resolved_data_sources),
            )
            response = self._request("POST", "/mira/api/v1/chat/create", json=payload)
            raw_payload = response.json()
            biz_code, biz_msg, biz_log_id = self._extract_biz_error(raw_payload)
            normalized = self._normalize_payload(raw_payload)
            session_id = self._find_first_string(
                normalized,
                ("sessionId", "session_id"),
            )
            if session_id:
                logger.info(
                    "Mira create_session succeeded: attempt=%d variant=%s session_id=%s",
                    attempt,
                    variant_name,
                    session_id,
                )
                return session_id

            if biz_code is not None:
                saw_session_invalid = saw_session_invalid or biz_code == 20001
                logger.warning(
                    "Mira create_session business error: attempt=%d variant=%s code=%s log_id=%s msg=%s",
                    attempt,
                    variant_name,
                    biz_code,
                    biz_log_id or "-",
                    biz_msg or "-",
                )
                last_error = f"code={biz_code}, msg={biz_msg}, log_id={biz_log_id}"
            else:
                last_top_keys = sorted(normalized.keys()) if isinstance(normalized, dict) else []
                logger.warning(
                    "Mira create_session missing sessionId: attempt=%d variant=%s top_keys=%s",
                    attempt,
                    variant_name,
                    last_top_keys,
                )

        if saw_session_invalid:
            role_context = self._get_role_context()
            if not self._has_role_context(role_context):
                raise ValueError(
                    "Mira create_session 失败: code=20001, msg=session invalid. "
                    "Current Mira role context is empty; GET /devops/get_role returned no "
                    "identity fields. This JWT/base URL combination cannot create chat "
                    "sessions until the Mira role context is initialized."
                )

        if last_error:
            raise ValueError(f"Mira create_session 失败: {last_error}")
        raise ValueError(
            f"Mira create_session 响应缺少 sessionId: top_keys={last_top_keys}"
        )

    async def send_message_stream(
        self,
        session_id: str,
        content: str,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        url = f"{self._config.base_url.rstrip('/')}/mira/api/v1/chat/completion"
        summary_agent = str((config or {}).get("model") or self._config.default_model).strip()
        payload = {
            "sessionId": session_id,
            "content": content,
            "messageType": 1,
            "summaryAgent": summary_agent,
            "dataSources": [],
            "comprehensive": 0,
        }
        if config:
            payload["config"] = config

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    yield json.loads(raw)

    def send_message_sync(
        self,
        session_id: str,
        content: str,
        config: dict[str, Any] | None = None,
    ) -> MiraMessageResponse:
        logger.info(
            "Mira send_message_sync start: session_id=%s content_len=%d config_keys=%s",
            session_id,
            len(content),
            sorted(config.keys()) if config else [],
        )
        chunks = list(_run_sync(self._collect_stream(session_id, content, config)))
        response = self._assemble_response(chunks)
        if not response.content:
            logger.warning(
                "Mira send_message_sync assembled empty content: session_id=%s event_tail=%s",
                session_id,
                self._summarize_event_tail(chunks),
            )
            polled_response = self._poll_message_response(
                session_id=session_id,
                min_round=response.round_index or None,
            )
            if polled_response is not None:
                logger.info(
                    "Mira send_message_sync recovered content via message polling: "
                    "session_id=%s message_id=%s round_index=%s response_len=%d",
                    session_id,
                    polled_response.message_id or "-",
                    polled_response.round_index,
                    len(polled_response.content),
                )
                response = polled_response
        logger.info(
            "Mira send_message_sync done: session_id=%s events=%d response_len=%d",
            session_id,
            len(chunks),
            len(response.content),
        )
        return response

    async def _collect_stream(
        self,
        session_id: str,
        content: str,
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        async for event in self.send_message_stream(session_id, content, config):
            normalized_events = self._normalize_stream_event(event)
            if normalized_events:
                chunks.extend(normalized_events)
        return chunks

    def get_messages(
        self,
        session_id: str,
        *,
        start_round: int | None = None,
        end_round: int | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "sessionId": session_id,
            "pagination": {
                "pageSize": 100,
                "pageNumber": 1,
            },
        }
        if start_round is not None:
            payload["startRound"] = start_round
        if end_round is not None:
            payload["endRound"] = end_round

        response = self._request("POST", "/mira/api/v1/chat/messages", json=payload)
        raw_payload = response.json()
        normalized = self._normalize_payload(raw_payload)
        raw_messages = normalized.get("messages", []) if isinstance(normalized, dict) else []
        if not isinstance(raw_messages, list):
            return []
        messages = [item for item in raw_messages if isinstance(item, dict)]
        logger.info(
            "Mira get_messages: session_id=%s start_round=%s end_round=%s count=%d tail=%s",
            session_id,
            start_round,
            end_round,
            len(messages),
            self._summarize_message_tail(messages),
        )
        return messages

    def delete_session(self, session_id: str) -> bool:
        logger.info("Mira delete_session start: session_id=%s", session_id)
        response = self._request(
            "POST",
            "/api/v1/chat/delete",
            json={"sessionId": session_id},
        )
        if not response.content:
            logger.info("Mira delete_session done: session_id=%s success=True", session_id)
            return True
        payload = response.json()
        success = bool(payload.get("success", payload.get("code", 0) == 0))
        logger.info("Mira delete_session done: session_id=%s success=%s", session_id, success)
        return success

    def get_models(self) -> list[MiraModelMetadata]:
        response = self._request("GET", "/api/v1/model/metadata")
        payload = self._normalize_payload(response.json())
        items = payload.get("models", payload.get("modelList", payload))
        if not isinstance(items, list):
            return []
        return [
            MiraModelMetadata(
                model=str(item.get("model", item.get("name", ""))),
                display_name=str(item.get("displayName", item.get("name", ""))),
                raw_extra=item if isinstance(item, dict) else {},
            )
            for item in items
            if isinstance(item, dict)
        ]

    def upload_files(self, files: list[Path]) -> list[MiraFileInfo]:
        uploaded: list[MiraFileInfo] = []
        for file_path in files:
            with file_path.open("rb") as handle:
                response = self._request(
                    "POST",
                    "/mira/api/v1/file/upload",
                    files={"file": (file_path.name, handle)},
                )
            payload = self._normalize_payload(response.json())
            items = payload.get("files", payload.get("fileList", [payload]))
            for item in items:
                if not isinstance(item, dict):
                    continue
                uploaded.append(
                    MiraFileInfo(
                        file_name=str(item.get("fileName", file_path.name)),
                        url=str(item.get("url", "")),
                        uri=str(item.get("uri", "")),
                        mime_type=str(item.get("mimeType", "")),
                        is_sensitive=bool(item.get("isSensitive", False)),
                    )
                )
        return uploaded

    def _assemble_response(self, events: list[dict[str, Any]]) -> MiraMessageResponse:
        content = self._extract_final_content(events)
        final_event = events[-1] if events else {}
        tasks = [
            event["task"]
            for event in events
            if isinstance(event.get("task"), dict)
        ]
        return MiraMessageResponse(
            message_id=self._find_first_string(final_event, ("messageId", "message_id", "id")),
            content=content,
            content_type=(
                self._find_first_string(final_event, ("contentType", "content_type")) or "text"
            ),
            round_index=self._find_first_int(final_event, ("roundIndex", "round_index")) or 0,
            tasks=tasks,
            raw_extra={"events": events},
        )

    def _extract_final_content(self, events: list[dict[str, Any]]) -> str:
        for event in reversed(events):
            text = self._extract_content_from_event(event)
            if text:
                return text

        fragments: list[str] = []
        for event in events:
            fragment = self._extract_delta_from_event(event)
            if fragment:
                fragments.append(fragment)
        return "".join(fragments)

    def _extract_content_from_event(self, event: dict[str, Any]) -> str:
        return self._extract_text_from_payload(
            event,
            (
                "content",
                "text",
                "answer",
                "outputText",
                "output_text",
                "finalContent",
                "value",
                "result",
            ),
            skip_keys=("delta",),
        )

    def _extract_delta_from_event(self, event: dict[str, Any]) -> str:
        delta = self._find_first_value(event, ("delta",))
        if delta is None:
            return ""
        return self._extract_text_from_payload(
            delta,
            ("content", "text", "answer", "outputText", "output_text", "value"),
        )

    def _find_first_value(
        self,
        payload: Any,
        candidate_keys: tuple[str, ...],
    ) -> Any:
        if isinstance(payload, dict):
            for key in candidate_keys:
                if key in payload:
                    return payload[key]
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    found = self._find_first_value(value, candidate_keys)
                    if found is not None:
                        return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_value(item, candidate_keys)
                if found is not None:
                    return found
        return None

    def _extract_text_from_payload(
        self,
        payload: Any,
        candidate_keys: tuple[str, ...],
        *,
        skip_keys: tuple[str, ...] = (),
    ) -> str:
        if isinstance(payload, str):
            return payload.strip()

        if isinstance(payload, list):
            fragments = [
                self._extract_text_from_payload(item, candidate_keys, skip_keys=skip_keys)
                for item in payload
            ]
            return "".join(fragment for fragment in fragments if fragment)

        if not isinstance(payload, dict):
            return ""

        for key in candidate_keys:
            if key in skip_keys:
                continue
            if key in payload:
                extracted = self._extract_text_from_payload(
                    payload[key],
                    candidate_keys,
                    skip_keys=skip_keys,
                )
                if extracted:
                    return extracted

        payload_type = str(payload.get("type", "")).strip().lower()
        if payload_type in {"text", "output_text", "markdown", "json"}:
            for key in ("text", "content", "value"):
                if key in skip_keys:
                    continue
                if key in payload:
                    extracted = self._extract_text_from_payload(
                        payload[key],
                        candidate_keys,
                        skip_keys=skip_keys,
                    )
                    if extracted:
                        return extracted

        for key, value in payload.items():
            if key in skip_keys:
                continue
            if isinstance(value, (dict, list)):
                extracted = self._extract_text_from_payload(
                    value,
                    candidate_keys,
                    skip_keys=skip_keys,
                )
                if extracted:
                    return extracted

        return ""

    def _find_first_int(
        self,
        payload: Any,
        candidate_keys: tuple[str, ...],
    ) -> int | None:
        if isinstance(payload, dict):
            for key in candidate_keys:
                value = payload.get(key)
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value.strip())
            for value in payload.values():
                found = self._find_first_int(value, candidate_keys)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_int(item, candidate_keys)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _summarize_event_tail(events: list[dict[str, Any]], limit: int = 3) -> str:
        tail = events[-limit:]
        try:
            rendered = json.dumps(tail, ensure_ascii=False)
        except TypeError:
            rendered = str(tail)
        if len(rendered) > 1500:
            rendered = rendered[:1500] + "...(truncated)"
        return rendered

    def _summarize_message_tail(self, messages: list[dict[str, Any]], limit: int = 3) -> str:
        tail = []
        for message in messages[-limit:]:
            tail.append(
                {
                    "messageId": self._find_first_string(message, ("messageId", "message_id", "id")),
                    "sender": message.get("sender", ""),
                    "roundIndex": self._find_first_int(message, ("roundIndex", "round_index")) or 0,
                    "sequence": self._find_first_int(message, ("sequence",)) or 0,
                    "timestamp": self._find_first_int(message, ("timestamp",)) or 0,
                    "content_len": len(
                        self._extract_text_from_payload(
                            message,
                            (
                                "content",
                                "text",
                                "answer",
                                "outputText",
                                "output_text",
                                "finalContent",
                                "value",
                                "result",
                            ),
                        )
                    ),
                }
            )
        try:
            rendered = json.dumps(tail, ensure_ascii=False)
        except TypeError:
            rendered = str(tail)
        if len(rendered) > 800:
            rendered = rendered[:800] + "...(truncated)"
        return rendered

    def _normalize_stream_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(event, dict):
            return []

        if event.get("done") is True:
            return []

        envelope = event.get("e")
        if isinstance(envelope, str) and envelope.strip():
            try:
                decoded = json.loads(envelope)
            except json.JSONDecodeError:
                logger.warning(
                    "Mira stream event envelope JSON decode failed: raw=%s",
                    envelope[:500],
                )
                return [event]
            if isinstance(decoded, dict):
                return self._normalize_stream_event(decoded)
            return []

        if isinstance(envelope, dict):
            return self._normalize_stream_event(envelope)

        return [event]

    def _poll_message_response(
        self,
        *,
        session_id: str,
        min_round: int | None = None,
    ) -> MiraMessageResponse | None:
        attempts = min(
            self._MESSAGE_POLL_ATTEMPTS,
            max(1, int(self._config.timeout_seconds)),
        )
        for attempt in range(1, attempts + 1):
            messages = self.get_messages(session_id, start_round=min_round)
            candidate = self._select_assistant_message(messages, min_round=min_round)
            logger.info(
                "Mira message polling: session_id=%s attempt=%d/%d message_count=%d found=%s",
                session_id,
                attempt,
                attempts,
                len(messages),
                bool(candidate and candidate.content),
            )
            if candidate and candidate.content:
                return candidate
            if attempt < attempts:
                time.sleep(self._MESSAGE_POLL_INTERVAL_SECONDS)
        return None

    def _select_assistant_message(
        self,
        messages: list[dict[str, Any]],
        *,
        min_round: int | None = None,
    ) -> MiraMessageResponse | None:
        assistant_candidates: list[tuple[tuple[int, int, int, int], MiraMessageResponse]] = []
        fallback_candidates: list[tuple[tuple[int, int, int, int], MiraMessageResponse]] = []

        for index, message in enumerate(messages):
            round_index = self._find_first_int(message, ("roundIndex", "round_index")) or 0
            if min_round is not None and round_index < min_round:
                continue

            content = self._extract_text_from_payload(
                message,
                (
                    "content",
                    "text",
                    "answer",
                    "outputText",
                    "output_text",
                    "finalContent",
                    "value",
                    "result",
                ),
            )
            if not content:
                continue

            candidate = MiraMessageResponse(
                message_id=self._find_first_string(message, ("messageId", "message_id", "id")),
                content=content,
                content_type=(
                    self._find_first_string(message, ("contentType", "content_type")) or "text"
                ),
                round_index=round_index,
                tasks=[],
                raw_extra={"message": message},
            )

            sort_key = (
                round_index,
                self._find_first_int(message, ("sequence",)) or 0,
                self._find_first_int(message, ("timestamp",)) or 0,
                index,
            )

            if self._is_assistant_sender(message.get("sender")):
                assistant_candidates.append((sort_key, candidate))
            else:
                fallback_candidates.append((sort_key, candidate))

        if assistant_candidates:
            assistant_candidates.sort(key=lambda item: item[0], reverse=True)
            return assistant_candidates[0][1]
        if fallback_candidates:
            fallback_candidates.sort(key=lambda item: item[0], reverse=True)
            return fallback_candidates[0][1]
        return None

    @staticmethod
    def _is_assistant_sender(sender: Any) -> bool:
        if isinstance(sender, int):
            return sender == 2
        normalized = str(sender).strip().lower()
        return normalized in {"2", "assistant", "agent", "bot", "ai"}
