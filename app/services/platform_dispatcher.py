"""平台分发器。

统一管理运行产物的持久化和多平台交付逻辑：
1. 持久化本地产物（JSON、Markdown 等）
2. 如果配置了 XMind 交付代理，执行 XMind 交付
3. 返回合并后的产物路径字典

变更：
- 使用共享的 markdown_renderer 替代内联 _render_test_cases_markdown（DRY 修复）
- 传递 optimized_tree 到 Markdown 渲染器
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from app.services.markdown_renderer import render_test_cases_markdown

if TYPE_CHECKING:
    from app.domain.api_models import CaseGenerationRun
    from app.repositories.run_repository import FileRunRepository
    from app.services.xmind_delivery_agent import XMindDeliveryAgent

logger = logging.getLogger(__name__)


class PlatformDispatcher:
    """平台分发器。"""

    def __init__(
        self,
        repository: FileRunRepository,
        xmind_agent: XMindDeliveryAgent | None = None,
        xmind_agent_factory: Callable[[Path], XMindDeliveryAgent] | None = None,
    ) -> None:
        self.repository = repository
        self.xmind_agent = xmind_agent
        self.xmind_agent_factory = xmind_agent_factory

    def dispatch(
        self,
        run_id: str,
        run: CaseGenerationRun,
        workflow_result: dict,
    ) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        artifacts.update(
            self._persist_local_artifacts(run_id, run, workflow_result)
        )
        run_dir = self.repository._run_dir(run_id)

        effective_agent = None
        if self.xmind_agent_factory is not None:
            try:
                effective_agent = self.xmind_agent_factory(run_dir)
            except Exception as exc:
                logger.exception(
                    "XMind agent 工厂创建失败: run_id=%s, error=%s", run_id, exc
                )
        elif self.xmind_agent is not None:
            effective_agent = self.xmind_agent

        if effective_agent is not None:
            try:
                xmind_result = effective_agent.deliver(
                    run_id=run_id,
                    test_cases=run.test_cases,
                    checkpoints=workflow_result.get("checkpoints", []),
                    research_output=run.research_summary,
                    title=run.input.file_path if run.input else "",
                    output_dir=run_dir,
                )
                if xmind_result.success:
                    artifacts["xmind_file"] = xmind_result.file_path
                    logger.info("XMind 交付成功: %s", xmind_result.file_path)
                else:
                    logger.warning(
                        "XMind 交付未成功: %s", xmind_result.error_message
                    )
                delivery_meta_path = run_dir / "xmind_delivery.json"
                if delivery_meta_path.exists():
                    artifacts["xmind_delivery"] = str(delivery_meta_path)
            except Exception as exc:
                logger.exception(
                    "XMind 交付过程发生未预期异常: run_id=%s, error=%s",
                    run_id,
                    exc,
                )

        return artifacts

    def _persist_local_artifacts(
        self,
        run_id: str,
        run: CaseGenerationRun,
        workflow_result: dict,
    ) -> dict[str, str]:
        artifacts: dict[str, str] = {}

        if run.parsed_document is not None:
            artifacts["parsed_document"] = str(
                self.repository.save(
                    run_id,
                    run.parsed_document.model_dump(mode="json"),
                    "parsed_document.json",
                )
            )
        if run.research_summary is not None:
            artifacts["research_output"] = str(
                self.repository.save(
                    run_id,
                    run.research_summary.model_dump(mode="json"),
                    "research_output.json",
                )
            )

        checkpoints = workflow_result.get("checkpoints", [])
        if checkpoints:
            artifacts["checkpoints"] = str(
                self.repository.save(
                    run_id,
                    [cp.model_dump(mode="json") for cp in checkpoints],
                    "checkpoints.json",
                )
            )

        checkpoint_coverage = workflow_result.get("checkpoint_coverage", [])
        if checkpoint_coverage:
            artifacts["checkpoint_coverage"] = str(
                self.repository.save(
                    run_id,
                    [cc.model_dump(mode="json") for cc in checkpoint_coverage],
                    "checkpoint_coverage.json",
                )
            )

        artifacts["test_cases"] = str(
            self.repository.save(
                run_id,
                [case.model_dump(mode="json") for case in run.test_cases],
                "test_cases.json",
            )
        )

        # 使用共享 Markdown 渲染器，传递 optimized_tree
        optimized_tree = workflow_result.get("optimized_tree", [])
        artifacts["test_cases_markdown"] = str(
            self.repository.save_text(
                run_id,
                "test_cases.md",
                render_test_cases_markdown(run.test_cases, optimized_tree),
            )
        )
        artifacts["quality_report"] = str(
            self.repository.save(
                run_id,
                run.quality_report.model_dump(mode="json"),
                "quality_report.json",
            )
        )

        return artifacts
