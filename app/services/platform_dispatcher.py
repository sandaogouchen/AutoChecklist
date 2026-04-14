"""平台分发器。

统一管理运行产物的持久化和多平台交付逻辑：
1. 持久化本地产物（JSON、Markdown 等）
2. 如果配置了 XMind 交付代理，执行 XMind 交付
3. 返回合并后的产物路径字典

变更：
- 使用共享的 markdown_renderer 替代内联 _render_test_cases_markdown（DRY 修复）
- 传递 optimized_tree 到 Markdown 渲染器
- 新增 draft_writer_timing.json 持久化（并发补充阶段耗时数据）
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
                    optimized_tree=workflow_result.get("optimized_tree", []),
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

        draft_cases = workflow_result.get("draft_cases")
        if draft_cases is not None:
            artifacts["draft_cases"] = str(
                self.repository.save(
                    run_id,
                    [case.model_dump(mode="json") for case in draft_cases],
                    "draft_cases.json",
                )
            )

        planned_scenarios = workflow_result.get("planned_scenarios")
        if planned_scenarios is not None:
            artifacts["planned_scenarios"] = str(
                self.repository.save(
                    run_id,
                    [scenario.model_dump(mode="json") for scenario in planned_scenarios],
                    "planned_scenarios.json",
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

        checkpoint_paths = workflow_result.get("checkpoint_paths")
        if checkpoint_paths is not None:
            artifacts["checkpoint_paths"] = str(
                self.repository.save(
                    run_id,
                    [path.model_dump(mode="json") for path in checkpoint_paths],
                    "checkpoint_paths.json",
                )
            )

        canonical_outline_nodes = workflow_result.get("canonical_outline_nodes")
        if canonical_outline_nodes is not None:
            artifacts["canonical_outline_nodes"] = str(
                self.repository.save(
                    run_id,
                    [node.model_dump(mode="json") for node in canonical_outline_nodes],
                    "canonical_outline_nodes.json",
                )
            )

        mapped_evidence = workflow_result.get("mapped_evidence")
        if mapped_evidence is not None:
            artifacts["mapped_evidence"] = str(
                self.repository.save(
                    run_id,
                    {
                        title: [item.model_dump(mode="json") for item in evidence_list]
                        for title, evidence_list in mapped_evidence.items()
                    },
                    "mapped_evidence.json",
                )
            )

        optimized_tree = workflow_result.get("optimized_tree")
        if optimized_tree is not None:
            artifacts["optimized_tree"] = str(
                self.repository.save(
                    run_id,
                    [node.model_dump(mode="json") for node in optimized_tree],
                    "optimized_tree.json",
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
        markdown_tree = workflow_result.get("optimized_tree", [])
        artifacts["test_cases_markdown"] = str(
            self.repository.save_text(
                run_id,
                "test_cases.md",
                render_test_cases_markdown(run.test_cases, markdown_tree),
            )
        )
        artifacts["quality_report"] = str(
            self.repository.save(
                run_id,
                run.quality_report.model_dump(mode="json"),
                "quality_report.json",
            )
        )

        # ---- draft_writer 并发耗时数据持久化 ----
        draft_writer_timing = workflow_result.get("draft_writer_timing")
        if draft_writer_timing:
            artifacts["draft_writer_timing"] = str(
                self.repository.save(
                    run_id,
                    draft_writer_timing,
                    "draft_writer_timing.json",
                )
            )
            logger.info(
                "draft_writer_timing.json 已保存: run_id=%s, batches=%d, elapsed=%.1fs",
                run_id,
                draft_writer_timing.get("total_batches", 0),
                draft_writer_timing.get("total_elapsed_seconds", 0),
            )

        return artifacts
