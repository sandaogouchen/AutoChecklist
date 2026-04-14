"""Mira 代码分析服务。"""

from __future__ import annotations

import logging
from typing import Any

from app.clients.mira_client import MiraClient, MiraClientConfig
from app.domain.mr_models import (
    CodeConsistencyResult,
    ConsistencyIssue,
    MRAnalysisResult,
    MRCodeFact,
    RelatedCodeSnippet,
)
from app.services.coco_client import Task1Response, Task2Response, build_task2_prompt
from app.services.coco_response_validator import CocoResponseValidator

logger = logging.getLogger(__name__)


def mira_code_analysis_enabled(llm_client: Any) -> bool:
    """判断是否启用 Mira 代码分析。"""
    config = getattr(llm_client, "config", None)
    return bool(getattr(config, "mira_use_for_code_analysis", False))


class MiraAnalysisService:
    """通过 Mira 会话接口执行 MR 分析和 checkpoint 校验。"""

    def __init__(self, llm_client: Any) -> None:
        self._llm_client = llm_client
        config = getattr(llm_client, "config", llm_client)

        base_url = str(getattr(config, "mira_api_base_url", "")).strip()
        jwt_token = str(getattr(config, "mira_jwt_token", "")).strip()
        session_cookie = str(getattr(config, "mira_cookie", "")).strip()
        if not base_url:
            raise ValueError("启用 Mira 代码分析时必须配置 MIRA_API_BASE_URL")
        if not jwt_token and not session_cookie:
            raise ValueError("启用 Mira 代码分析时必须配置 MIRA_JWT_TOKEN 或 MIRA_COOKIE")

        self._model = str(getattr(config, "model", getattr(config, "llm_model", "")))
        self._client = MiraClient(
            MiraClientConfig(
                base_url=base_url,
                jwt_token=jwt_token,
                session_cookie=session_cookie,
                default_model=self._model,
                timeout_seconds=float(getattr(config, "timeout_seconds", 300.0)),
                timezone=str(getattr(config, "timezone", "Asia/Shanghai")),
                client_version=str(
                    getattr(config, "mira_client_version", "autochecklist/0.1.0")
                ),
            )
        )
        self._validator = CocoResponseValidator(llm_client)
        logger.info(
            "MiraAnalysisService initialized: model=%s timeout=%.1fs timezone=%s",
            self._model or "<default>",
            float(getattr(config, "timeout_seconds", 300.0)),
            str(getattr(config, "timezone", "Asia/Shanghai")),
        )

    async def run_mr_analysis_task(
        self,
        *,
        mr_context: dict[str, str],
        prd_summary: str,
        changed_files_summary: str,
    ) -> tuple[MRAnalysisResult, dict[str, Any]]:
        from app.nodes.mr_analyzer import _build_coco_task1_prompt

        prompt = _build_coco_task1_prompt(
            mr_url=mr_context.get("mr_url", ""),
            git_url=mr_context.get("git_url", ""),
            branch=mr_context.get("branch", ""),
            prd_summary=prd_summary,
            changed_files_summary=changed_files_summary,
        )
        session_id = self._client.create_session(
            topic="autochecklist-mr-analysis",
            model=self._model,
            data_sources=[],
        )
        logger.info(
            "Mira MR analysis started: session_id=%s mr_url=%s branch=%s prompt_len=%d",
            session_id,
            mr_context.get("mr_url", ""),
            mr_context.get("branch", ""),
            len(prompt),
        )
        try:
            response = self._client.send_message_sync(session_id, prompt)
            parsed, meta = await self._validator.validate_and_fix(
                response.content,
                Task1Response,
                context=f"MR={mr_context.get('mr_url', '')}",
            )
            result = MRAnalysisResult(
                mr_summary=parsed.mr_summary,
                changed_modules=list(parsed.changed_modules),
                related_code_snippets=[
                    RelatedCodeSnippet(
                        file_path=item.file_path,
                        code_content=item.code_content,
                        relation_type=item.relation_type,
                    )
                    for item in parsed.related_code_snippets
                ],
                code_facts=[
                    MRCodeFact(
                        fact_id=item.fact_id,
                        description=item.description,
                        source_file=item.source_file,
                        code_snippet=item.code_snippet,
                        fact_type=item.fact_type,
                        related_prd_fact_ids=list(item.related_prd_fact_ids),
                    )
                    for item in parsed.code_facts
                ],
                consistency_issues=[
                    ConsistencyIssue(
                        issue_id=item.issue_id,
                        severity=item.severity,
                        prd_expectation=item.prd_expectation,
                        mr_implementation=item.mr_implementation,
                        discrepancy=item.discrepancy,
                        confidence=item.confidence,
                    )
                    for item in parsed.consistency_issues
                ],
                search_trace=[f"mira:{meta.get('layer', 'unknown')}"],
            )
            logger.info(
                "Mira MR analysis completed: session_id=%s response_len=%d layer=%s facts=%d issues=%d",
                session_id,
                len(response.content),
                meta.get("layer", "unknown"),
                len(result.code_facts),
                len(result.consistency_issues),
            )
            return result, {
                "prompt": prompt,
                "session_id": session_id,
                "task_id": session_id,
                "task": {
                    "session_id": session_id,
                    "raw_events": response.raw_extra.get("events", []),
                },
                "response": response.content,
                "result": result,
                "meta": meta,
            }
        finally:
            try:
                self._client.delete_session(session_id)
                logger.info("Mira MR analysis session cleaned up: session_id=%s", session_id)
            except Exception:
                logger.warning(
                    "Mira MR analysis session cleanup failed: session_id=%s",
                    session_id,
                    exc_info=True,
                )

    async def run_validation_task(
        self,
        checkpoint: Any,
        mr_context: dict[str, str],
    ) -> tuple[CodeConsistencyResult, dict[str, Any]]:
        prompt = build_task2_prompt(checkpoint, mr_context)
        session_id = self._client.create_session(
            topic="autochecklist-code-validation",
            model=self._model,
            data_sources=[],
        )
        logger.info(
            "Mira validation started: session_id=%s checkpoint=%s prompt_len=%d",
            session_id,
            getattr(checkpoint, "checkpoint_id", ""),
            len(prompt),
        )
        try:
            response = self._client.send_message_sync(session_id, prompt)
            parsed, meta = await self._validator.validate_and_fix(
                response.content,
                Task2Response,
                context=f"checkpoint={getattr(checkpoint, 'checkpoint_id', '')}",
            )
            result = CodeConsistencyResult(
                status="confirmed" if parsed.is_consistent else "mismatch",
                confidence=max(0.0, min(1.0, parsed.confidence)),
                actual_implementation=parsed.actual_implementation,
                inconsistency_reason=parsed.inconsistency_reason,
                related_code_file=parsed.related_code_file,
                related_code_snippet=parsed.related_code_snippet,
                verified_by="mira",
            )
            logger.info(
                "Mira validation completed: session_id=%s checkpoint=%s response_len=%d layer=%s status=%s",
                session_id,
                getattr(checkpoint, "checkpoint_id", ""),
                len(response.content),
                meta.get("layer", "unknown"),
                result.status,
            )
            return result, {
                "prompt": prompt,
                "session_id": session_id,
                "task_id": session_id,
                "task": {
                    "session_id": session_id,
                    "raw_events": response.raw_extra.get("events", []),
                },
                "response": response.content,
                "result": result,
                "meta": meta,
            }
        finally:
            try:
                self._client.delete_session(session_id)
                logger.info("Mira validation session cleaned up: session_id=%s", session_id)
            except Exception:
                logger.warning(
                    "Mira validation session cleanup failed: session_id=%s",
                    session_id,
                    exc_info=True,
                )
