"""Coco Agent API 客户端封装。

负责与字节内部 Coco Agent（codebase-api.byted.org）进行异步通信，
包括任务发送、轮询等待、结果解析，以及三层容错处理。

支持两类任务：
- Task 1：MR 代码 case 生成（在 mr_analyzer 中调用）
- Task 2：逐 case 一致性校验（在 coco_consistency_validator 中调用）
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.domain.mr_models import (
    CodeConsistencyResult,
    ConsistencyIssue,
    CocoTaskStatus,
    MRAnalysisResult,
    MRCodeFact,
    RelatedCodeSnippet,
)
from app.services.prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)
_PROMPT_LOADER = get_prompt_loader()


def build_task2_prompt(
    checkpoint: Any,
    mr_context: dict[str, str],
) -> str:
    """构建 Task 2 提示词，强调仓库/分支/场景/预期与代码验证顺序。"""
    cp_name = getattr(checkpoint, "name", getattr(checkpoint, "title", ""))
    cp_desc = getattr(checkpoint, "description", "")
    cp_expected = getattr(
        checkpoint,
        "expected_result",
        getattr(checkpoint, "objective", ""),
    )
    cp_steps = getattr(checkpoint, "test_steps", "")
    if not cp_steps:
        cp_steps = "\n".join(getattr(checkpoint, "preconditions", [])[:5])

    return _PROMPT_LOADER.render(
        "services/coco_client/task2_user.md",
        mr_url=mr_context.get("mr_url", ""),
        git_url=mr_context.get("git_url", ""),
        branch=mr_context.get("branch", "unknown"),
        cp_name=cp_name,
        cp_desc=cp_desc,
        cp_expected=cp_expected,
        cp_steps=cp_steps,
    )


# ---------------------------------------------------------------------------
# 异常定义
# ---------------------------------------------------------------------------


class CocoTaskError(Exception):
    """Coco Agent 任务执行异常。"""

    def __init__(self, message: str, task_id: str = "", status: str = ""):
        super().__init__(message)
        self.task_id = task_id
        self.status = status


# ---------------------------------------------------------------------------
# Coco 响应 Pydantic Schema
# ---------------------------------------------------------------------------


class CodeFactItem(BaseModel):
    """Task 1 — 单条代码级事实。"""

    fact_id: str = ""
    description: str = ""
    source_file: str = ""
    fact_type: str = "logic_branch"
    severity: str = "medium"
    related_function: str = ""
    code_snippet: str = ""
    related_prd_fact_ids: list[str] = Field(default_factory=list)


class ConsistencyIssueItem(BaseModel):
    """Task 1 — 单条一致性问题。"""

    issue_id: str = ""
    severity: str = "major"
    prd_expectation: str = ""
    mr_implementation: str = ""
    discrepancy: str = ""
    confidence: float = 0.0


class RelatedSnippetItem(BaseModel):
    """Task 1 — 单条关联代码片段。"""

    file_path: str = ""
    code_content: str = ""
    relation_type: str = "caller"


class Task1Response(BaseModel):
    """Task 1 Coco 响应的完整 Schema（MR 代码 case 生成）。"""

    mr_summary: str = ""
    changed_modules: list[str] = Field(default_factory=list)
    code_facts: list[CodeFactItem] = Field(default_factory=list)
    consistency_issues: list[ConsistencyIssueItem] = Field(default_factory=list)
    related_code_snippets: list[RelatedSnippetItem] = Field(default_factory=list)


class Task2Response(BaseModel):
    """Task 2 Coco 响应的完整 Schema（逐 case 一致性校验）。"""

    is_consistent: bool = True
    confidence: float = 0.0
    actual_implementation: str = ""
    inconsistency_reason: str = ""
    related_code_file: str = ""
    related_code_snippet: str = ""


# ---------------------------------------------------------------------------
# Coco 客户端
# ---------------------------------------------------------------------------


class CocoClient:
    """Coco Agent API 客户端。

    封装 SendCopilotTaskMessage / GetCopilotTask 两个核心接口，
    并集成 CocoResponseValidator 做三层容错解析。

    Args:
        settings: Coco 配置对象（包含 base_url / jwt_token 等）。
        llm_client: LLM 客户端，用于 CocoResponseValidator 的 LLM 推断。
    """

    def __init__(self, settings: Any, llm_client: Any = None):
        self._settings = settings
        self._llm_client = llm_client
        self._base_url: str = getattr(settings, "coco_api_base_url", "https://codebase-api.byted.org/v2/")
        self._jwt_token: str = getattr(settings, "coco_jwt_token", "")
        self._agent_name: str = getattr(settings, "coco_agent_name", "sandbox")
        self._model_name: str = getattr(settings, "coco_model_name", "GPT-5.4")
        self._repo_id: str = getattr(settings, "coco_repo_id", "")
        self._branch: str = getattr(settings, "coco_branch", "")
        self._timeout: int = getattr(settings, "coco_task_timeout", 300)
        self._poll_start: int = getattr(settings, "coco_poll_interval_start", 5)
        self._poll_max: int = getattr(settings, "coco_poll_interval_max", 20)

    # ------------------------------------------------------------------
    # 内部请求
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """构建 HTTP 请求头。"""
        return {
            "Content-Type": "application/json",
            "X-Code-User-JWT": self._jwt_token,
        }

    @staticmethod
    def _parse_http_error(exc: httpx.HTTPStatusError) -> tuple[int, str, str]:
        """提取 HTTP 错误中的状态码、业务错误码和响应体。"""
        response_text = exc.response.text.strip()
        error_code = ""
        try:
            payload = exc.response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            error_code = (
                payload.get("ResponseMetadata", {})
                .get("Error", {})
                .get("Code", "")
            )
        return exc.response.status_code, error_code, response_text[:1000]

    @staticmethod
    def _resolve_agent_name(agent_name: str | None) -> str:
        """将 agent 名称约束到 OpenAPI 支持的取值范围。"""
        supported_agents = {"copilot", "sandbox"}
        normalized = (agent_name or "").strip().lower()
        if normalized in supported_agents:
            return normalized
        if normalized:
            logger.warning(
                "Coco agent_name=%s 不受 OpenAPI 支持，自动回退为 sandbox",
                agent_name,
            )
        return "sandbox"

    def _build_action_url(self, action: str) -> str:
        """构造 Coco OpenAPI Action URL，遵循官方 /v2/?Action=... 形式。"""
        return f"{self._base_url.rstrip('/')}/?Action={action}"

    async def _post(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求到 Coco API。"""
        url = self._build_action_url(action)
        logger.debug("Coco API 请求: %s, payload keys=%s", action, list(payload.keys()))
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                response_text = exc.response.text.strip()
                if response_text:
                    logger.error(
                        "Coco API %s 失败: status=%s, response=%s",
                        action,
                        exc.response.status_code,
                        response_text[:1000],
                    )
                raise
            data = resp.json()

        if "Result" not in data:
            raise CocoTaskError(f"Coco API 响应异常: 缺少 Result 字段, action={action}")
        return data["Result"]

    async def _collect_task_messages_via_sse(
        self,
        task_id: str,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """通过 SSE 订阅收集 full_message 事件中的消息。"""
        url = self._build_action_url("SubscribeCopilotTaskEvents")
        max_wait = max(float(timeout or self._timeout), 10.0)
        messages: list[dict[str, Any]] = []
        logger.info("开始订阅 Coco SSE: task_id=%s, timeout=%.1fs", task_id, max_wait)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=30.0, read=max_wait, write=30.0, pool=30.0),
                follow_redirects=True,
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json={"TaskId": task_id},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = (line or "").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        raw_payload = line[len("data:"):].strip()
                        if not raw_payload:
                            continue
                        try:
                            payload = json.loads(raw_payload)
                        except json.JSONDecodeError:
                            logger.debug("Coco SSE 事件解析失败: task_id=%s, payload=%s", task_id, raw_payload[:500])
                            continue

                        event = payload.get("Event", {})
                        event_type = event.get("Type", "")
                        detail = event.get("Detail", {})

                        if event_type == "full_message":
                            message = detail.get("FullMessage", {}).get("Message", {})
                            if message:
                                messages.append(message)
                            continue

                        if event_type == "task_status_update":
                            update = detail.get("TaskStatusUpdate", {})
                            if update.get("Final"):
                                logger.info(
                                    "Coco SSE 结束: task_id=%s, final_status=%s, messages=%d",
                                    task_id,
                                    update.get("Status", ""),
                                    len(messages),
                                )
                                break
        except httpx.HTTPError as exc:
            logger.warning("Coco SSE 订阅失败: task_id=%s, error=%s", task_id, exc)
            return []

        logger.info("Coco SSE 收集完成: task_id=%s, messages=%d", task_id, len(messages))
        return messages

    # ------------------------------------------------------------------
    # Task 发送
    # ------------------------------------------------------------------

    async def send_task(
        self,
        prompt: str,
        mr_url: str = "",
        git_url: str = "",
        agent_name: str | None = None,
    ) -> str:
        """向 Coco 发送代码分析任务。

        Args:
            prompt: 分析 prompt（包含任务要求和输出格式）。
            mr_url: MR 链接。
            git_url: Git 仓库链接。
            agent_name: Coco agent 类型，默认使用配置值。

        Returns:
            Coco 任务 ID。

        Raises:
            CocoTaskError: 发送失败。
        """
        if not self._jwt_token:
            raise CocoTaskError("COCO_JWT_TOKEN 未配置，无法使用 Coco Agent")

        payload = {
            "AgentName": self._resolve_agent_name(agent_name or self._agent_name),
            "Message": {
                "Id": "",
                "Role": "user",
                "Parts": [{"Text": {"Text": prompt}}],
            },
        }
        if self._model_name.strip():
            payload["modelName"] = self._model_name.strip()
        if self._repo_id.strip():
            payload['repoId'] = self._model_name.strip()
        if self._branch.strip():
            payload['branch'] = self._branch.strip()
        payload['disable_model_failover']='true'

        try:
            result = await self._post("SendCopilotTaskMessage", payload)
            task_id = result.get("Task", {}).get("Id", "")
            if not task_id:
                raise CocoTaskError("Coco 返回的 Task.Id 为空")
            logger.info("Coco 任务已发送: task_id=%s, mr_url=%s", task_id, mr_url)
            return task_id
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text.strip()
            detail = f"{exc}"
            if response_text:
                detail = f"{detail}; response={response_text[:500]}"
            logger.error("Coco 任务发送失败 (HTTP): %s", detail)
            raise CocoTaskError(f"Coco 任务发送 HTTP 错误: {detail}") from exc
        except httpx.HTTPError as exc:
            logger.error("Coco 任务发送失败 (HTTP): %s", exc)
            raise CocoTaskError(f"Coco 任务发送 HTTP 错误: {exc}") from exc
        except CocoTaskError:
            raise
        except Exception as exc:
            logger.error("Coco 任务发送失败: %s", exc, exc_info=True)
            raise CocoTaskError(f"Coco 任务发送失败: {exc}") from exc

    # ------------------------------------------------------------------
    # Task 轮询
    # ------------------------------------------------------------------

    async def poll_task(
        self,
        task_id: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """轮询 Coco 任务状态直到完成。

        使用指数退避策略：5s -> 10s -> 15s -> 20s（上限 20s）。

        Args:
            task_id: Coco 任务 ID。
            timeout: 最大等待时间（秒），默认使用配置值。

        Returns:
            Coco 任务结果字典。

        Raises:
            TimeoutError: 超时未完成。
            CocoTaskError: 任务执行失败。
        """
        max_wait = timeout or self._timeout
        start = time.monotonic()
        poll_interval = self._poll_start
        not_found_grace_window = min(max_wait, 15)

        logger.info("开始轮询 Coco 任务: task_id=%s, timeout=%ds", task_id, max_wait)

        while time.monotonic() - start < max_wait:
            try:
                result = await self._post("GetCopilotTask", {"TaskId": task_id})
            except httpx.HTTPStatusError as exc:
                status_code, error_code, response_text = self._parse_http_error(exc)
                elapsed = time.monotonic() - start
                if status_code == 404 and error_code == "NotFound.Task":
                    if elapsed < not_found_grace_window:
                        logger.warning(
                            "Coco 任务暂不可见: task_id=%s, elapsed=%.1fs, 将重试",
                            task_id,
                            elapsed,
                        )
                        await asyncio.sleep(poll_interval)
                        poll_interval = min(poll_interval + 5, self._poll_max)
                        continue
                    raise CocoTaskError(
                        (
                            f"Coco 任务 {task_id} 查询失败: "
                            "GetCopilotTask 返回 NotFound.Task；"
                            "当前 task_id 可能并非可查询的实际任务 ID"
                        ),
                        task_id=task_id,
                        status="not_found",
                    ) from exc

                if 400 <= status_code < 500:
                    raise CocoTaskError(
                        (
                            f"Coco 任务 {task_id} 查询失败: HTTP {status_code}"
                            + (f", code={error_code}" if error_code else "")
                            + (f", response={response_text}" if response_text else "")
                        ),
                        task_id=task_id,
                    ) from exc

                logger.warning("Coco 轮询请求失败: %s, 将重试", exc)
                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval + 5, self._poll_max)
                continue
            except httpx.HTTPError as exc:
                logger.warning("Coco 轮询请求失败: %s, 将重试", exc)
                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval + 5, self._poll_max)
                continue

            task = result.get("Task", {})
            status = task.get("Status", "")
            elapsed = time.monotonic() - start

            logger.info(
                "Coco 任务状态: task_id=%s, status=%s, elapsed=%.1fs",
                task_id, status, elapsed,
            )

            if status == "completed":
                messages = await self._collect_task_messages_via_sse(
                    task_id,
                    timeout=max(10, int(max_wait - elapsed)),
                )
                if messages:
                    task = {**task, "Messages": messages}
                else:
                    logger.warning("Coco 任务完成但 SSE 未拿到消息: task_id=%s", task_id)
                logger.info("Coco 任务完成: task_id=%s, elapsed=%.1fs", task_id, elapsed)
                return task

            if status in ("failed", "cancelled"):
                error_msg = task.get("Error", "未知错误")
                raise CocoTaskError(
                    f"Coco 任务 {task_id} 状态={status}: {error_msg}",
                    task_id=task_id,
                    status=status,
                )

            await asyncio.sleep(min(poll_interval, self._poll_max))
            poll_interval += 5

        elapsed = time.monotonic() - start
        raise TimeoutError(f"Coco 任务 {task_id} 超时: {elapsed:.1f}s > {max_wait}s")

    # ------------------------------------------------------------------
    # 结果解析
    # ------------------------------------------------------------------

    @staticmethod
    def _get_assistant_text(task: dict[str, Any]) -> str:
        """从 Coco 任务结果中提取 assistant 回复文本。"""
        messages = task.get("Messages", [])
        for msg in reversed(messages):
            if msg.get("Role") in {"assistant", "agent"}:
                parts = msg.get("Parts", [])
                if parts:
                    text_obj = parts[0].get("Text", {})
                    return text_obj.get("Text", "")
        return ""

    async def extract_result(self, task: dict[str, Any]) -> MRAnalysisResult:
        """从 Coco Task 1 结果中提取 MRAnalysisResult。

        集成 CocoResponseValidator 进行三层容错解析。

        Args:
            task: Coco GetCopilotTask 返回的 Task 字典。

        Returns:
            解析后的 MRAnalysisResult。
        """
        parsed, meta = await self.extract_task1_payload(task)
        result = self._map_task1_to_result(parsed, meta)
        result.consistency_issues = []
        return result

    async def extract_task1_payload(
        self,
        task: dict[str, Any],
    ) -> tuple[Task1Response, dict[str, Any]]:
        """提取并解析 Task 1 原始响应。"""
        raw_text = self._get_assistant_text(task)
        if not raw_text:
            logger.warning("Coco 任务未返回有效文本，返回空结果")
            return Task1Response(mr_summary="Coco 未返回有效结果"), {
                "layer": "empty",
                "inferred_fields": [],
            }

        from app.services.coco_response_validator import CocoResponseValidator

        validator = CocoResponseValidator(self._llm_client)
        parsed, meta = await validator.validate_and_fix(
            raw_text,
            Task1Response,
            context="MR 代码变更分析任务",
        )

        logger.info(
            "Task1 解析路径: layer=%s, 推断字段=%s",
            meta.get("layer", "unknown"),
            meta.get("inferred_fields", []),
        )
        return parsed, meta

    @staticmethod
    def _map_task1_to_result(
        parsed: Task1Response,
        meta: dict[str, Any],
    ) -> MRAnalysisResult:
        """将 Task1Response 映射为 MRAnalysisResult。"""
        code_facts = [
            MRCodeFact(
                fact_id=f.fact_id or f"CF-{i + 1:03d}",
                description=f.description,
                source_file=f.source_file,
                code_snippet=f.code_snippet,
                fact_type=f.fact_type,
                related_prd_fact_ids=f.related_prd_fact_ids,
            )
            for i, f in enumerate(parsed.code_facts)
        ]
        consistency_issues = [
            ConsistencyIssue(
                issue_id=ci.issue_id or f"CI-{i + 1:03d}",
                severity=ci.severity,
                prd_expectation=ci.prd_expectation,
                mr_implementation=ci.mr_implementation,
                discrepancy=ci.discrepancy,
                confidence=ci.confidence,
            )
            for i, ci in enumerate(parsed.consistency_issues)
        ]
        related_snippets = [
            RelatedCodeSnippet(
                file_path=s.file_path,
                code_content=s.code_content,
                relation_type=s.relation_type,
            )
            for s in parsed.related_code_snippets
        ]

        search_trace = ["via_coco_agent"]
        if meta.get("layer") in ("3-partial", "3-full", "fallback-defaults"):
            search_trace.append(f"llm_infer_layer={meta['layer']}")

        return MRAnalysisResult(
            mr_summary=parsed.mr_summary,
            changed_modules=parsed.changed_modules,
            code_facts=code_facts,
            consistency_issues=consistency_issues,
            related_code_snippets=related_snippets,
            search_trace=search_trace,
        )

    async def run_mr_analysis_task(
        self,
        *,
        mr_context: dict[str, str],
        prd_summary: str,
        changed_files_summary: str,
    ) -> tuple[MRAnalysisResult, dict[str, Any]]:
        """Task 1 — 对单个 MR 上下文执行一次 Coco MR 分析。"""
        from app.nodes.mr_analyzer import _build_coco_task1_prompt

        prompt = _build_coco_task1_prompt(
            mr_url=mr_context.get("mr_url", ""),
            git_url=mr_context.get("git_url", ""),
            branch=mr_context.get("branch", ""),
            prd_summary=prd_summary,
            changed_files_summary=changed_files_summary,
        )
        task_id = await self.send_task(
            prompt=prompt,
            mr_url=mr_context.get("mr_url", ""),
            git_url=mr_context.get("git_url", ""),
        )
        task = await self.poll_task(task_id)
        result = await self.extract_result(task)
        logger.info(
            "Coco Task1 MR 分析完成: task_id=%s, summary=%s, code_facts=%d",
            task_id,
            (result.mr_summary or "")[:60],
            len(result.code_facts),
        )
        return result, {
            "prompt": prompt,
            "task_id": task_id,
            "task": task,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Task 2: 逐 case 一致性校验
    # ------------------------------------------------------------------

    async def send_validation_task(
        self,
        checkpoint: Any,
        mr_context: dict[str, str],
    ) -> CodeConsistencyResult:
        """Task 2 — 向 Coco 发送单个 checkpoint 的一致性校验请求。

        Args:
            checkpoint: Checkpoint 对象（需具有 name / description / expected_result 等属性）。
            mr_context: MR 上下文 ``{"mr_url": ..., "git_url": ...}``。

        Returns:
            CodeConsistencyResult。
        """
        try:
            result, _artifacts = await self.run_validation_task(checkpoint, mr_context)
            return result
        except (CocoTaskError, TimeoutError, Exception) as exc:
            logger.warning("Task2 校验失败 [%s]: %s", cp_name, exc)
            return CodeConsistencyResult(
                status="unverified",
                verified_by="",
            )

    async def run_validation_task(
        self,
        checkpoint: Any,
        mr_context: dict[str, str],
        timeout_s: int = 120,
    ) -> tuple[CodeConsistencyResult, dict[str, Any]]:
        """执行 Task 2 并返回结果及可落盘的原始工件。"""
        prompt = build_task2_prompt(checkpoint, mr_context)
        task_id = await self.send_task(
            prompt=prompt,
            mr_url=mr_context.get("mr_url", ""),
            git_url=mr_context.get("git_url", ""),
        )
        task = await self.poll_task(task_id, timeout=timeout_s)
        raw_text = self._get_assistant_text(task)
        result = await self._parse_validation_result(checkpoint, raw_text)
        return result, {
            "prompt": prompt,
            "task_id": task_id,
            "task": task,
            "result": result,
        }

    async def _parse_validation_result(
        self,
        checkpoint: Any,
        raw_text: str,
    ) -> CodeConsistencyResult:
        """解析 Task 2 原始文本为结构化结果。"""
        cp_name = getattr(checkpoint, "name", getattr(checkpoint, "title", ""))
        cp_desc = getattr(checkpoint, "description", "")

        if not raw_text:
            return CodeConsistencyResult(status="unverified", verified_by="")

        from app.services.coco_response_validator import CocoResponseValidator

        validator = CocoResponseValidator(self._llm_client)
        parsed, meta = await validator.validate_and_fix(
            raw_text,
            Task2Response,
            context=f"校验点: {cp_name} — {cp_desc[:100]}",
        )

        logger.info(
            "Task2 [%s] 解析路径: layer=%s, 推断字段=%s",
            cp_name,
            meta.get("layer", "unknown"),
            meta.get("inferred_fields", []),
        )

        verified_by = "coco"
        if meta.get("layer") in ("fallback-defaults",):
            verified_by = "coco+llm_fallback"

        return CodeConsistencyResult(
            status="mismatch" if not parsed.is_consistent else "confirmed",
            confidence=max(0.0, min(1.0, parsed.confidence)),
            actual_implementation=parsed.actual_implementation,
            inconsistency_reason=parsed.inconsistency_reason,
            related_code_file=parsed.related_code_file,
            related_code_snippet=parsed.related_code_snippet,
            verified_by=verified_by,
        )
