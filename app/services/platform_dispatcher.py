"""平台分发器。

统一管理运行产物的持久化和多平台交付逻辑：
1. 持久化本地产物（JSON、Markdown 等）
2. 如果配置了 XMind 交付代理（直接实例或工厂函数），执行 XMind 交付
3. 返回合并后的产物路径字典

XMind 交付失败不会导致整个分发流程失败。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from app.domain.case_models import TestCase

if TYPE_CHECKING:
    from app.domain.api_models import CaseGenerationRun
    from app.repositories.run_repository import FileRunRepository
    from app.services.xmind_delivery_agent import XMindDeliveryAgent

logger = logging.getLogger(__name__)


class PlatformDispatcher:
    """平台分发器。

    集中管理运行产物的持久化逻辑，并协调可选的平台交付（如 XMind）。
    支持两种 XMind 交付模式：
    - 直接传入 ``xmind_agent`` 实例（向后兼容）
    - 传入 ``xmind_agent_factory`` 工厂函数，每次 dispatch 时按 run_dir 动态创建 agent
    """

    def __init__(
        self,
        repository: FileRunRepository,
        xmind_agent: XMindDeliveryAgent | None = None,
        xmind_agent_factory: Callable[[Path], XMindDeliveryAgent] | None = None,
    ) -> None:
        """初始化平台分发器。

        Args:
            repository: 文件运行记录仓储。
            xmind_agent: XMind 交付代理（可选，向后兼容模式）。
            xmind_agent_factory: XMind 交付代理工厂函数（可选），
                接受 run_dir 参数并返回 XMindDeliveryAgent 实例。
                优先级高于 xmind_agent。
        """
        self.repository = repository
        self.xmind_agent = xmind_agent
        self.xmind_agent_factory = xmind_agent_factory

    def dispatch(
        self,
        run_id: str,
        run: CaseGenerationRun,
        workflow_result: dict,
    ) -> dict[str, str]:
        """执行产物持久化和平台交付。

        流程：
        1. 持久化本地产物（JSON + Markdown）
        2. 如果有 XMind 交付能力（工厂函数或直接 agent），执行 XMind 交付
        3. 合并并返回所有产物路径

        Args:
            run_id: 运行 ID。
            run: 运行结果对象。
            workflow_result: 工作流执行结果字典。

        Returns:
            产物路径字典，键为产物名称，值为文件路径。
        """
        artifacts: dict[str, str] = {}

        # 持久化本地产物
        artifacts.update(
            self._persist_local_artifacts(run_id, run, workflow_result)
        )

        # 获取运行目录路径
        run_dir = self.repository._run_dir(run_id)

        # XMind 交付（可选）
        # 优先使用工厂函数创建 per-run 的 agent，使 XMind 文件输出到运行目录
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

                # 无论成功与否，记录交付元数据路径
                delivery_meta_path = run_dir / "xmind_delivery.json"
                if delivery_meta_path.exists():
                    artifacts["xmind_delivery"] = str(delivery_meta_path)

            except Exception as exc:
                # XMind 失败绝不阻断主流程
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
        """持久化本地文件产物。

        Args:
            run_id: 运行 ID。
            run: 运行结果对象。
            workflow_result: 工作流执行结果字典。

        Returns:
            本地产物路径字典。
        """
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
        artifacts["test_cases_markdown"] = str(
            self.repository.save_text(
                run_id,
                "test_cases.md",
                _render_test_cases_markdown(run.test_cases),
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


def _render_test_cases_markdown(test_cases: list[TestCase]) -> str:
    """将测试用例列表渲染为人类可读的 Markdown 文档。

    使用中文标题以保持与中文优先输出策略的一致性。
    """
    if not test_cases:
        return "# 生成的测试用例\n\n暂无测试用例。\n"

    lines = ["# 生成的测试用例", ""]
    for test_case in test_cases:
        lines.append(f"## {test_case.id} {test_case.title}")
        lines.append("")

        if test_case.checkpoint_id:
            lines.append(f"**Checkpoint:** {test_case.checkpoint_id}")
            lines.append("")

        lines.append("### 前置条件")
        lines.extend(
            [f"- {item}" for item in test_case.preconditions] or ["- 无"]
        )
        lines.append("")
        lines.append("### 步骤")
        lines.extend(
            [f"{i}. {step}" for i, step in enumerate(test_case.steps, start=1)]
            or ["1. 无"]
        )
        lines.append("")
        lines.append("### 预期结果")
        lines.extend(
            [f"- {item}" for item in test_case.expected_results] or ["- 无"]
        )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
