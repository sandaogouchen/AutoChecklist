"""工作流编排服务。

作为 API 层与工作流引擎之间的协调者，负责：
- 创建运行任务并执行 LangGraph 工作流
- 管理迭代评估回路的生命周期
- 通过 PlatformDispatcher 持久化运行产物（JSON + Markdown + XMind）
- 持久化运行状态、评估报告和迭代日志
- 查询历史运行结果（包括失败运行）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.api_models import (
    CaseGenerationRequest,
    CaseGenerationRun,
    ErrorInfo,
    IterationSummary,
)
from app.domain.case_models import QualityReport, TestCase
from app.domain.run_state import RunStage, RunStatus
from app.graphs.main_workflow import build_workflow
from app.nodes.evaluation import evaluate
from app.nodes.project_context_loader import build_project_context_loader
from app.repositories.run_repository import FileRunRepository
from app.repositories.run_state_repository import RunStateRepository
from app.services.iteration_controller import IterationController
from app.services.platform_dispatcher import PlatformDispatcher
from app.services.project_context_service import ProjectContextService
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder
from app.utils.run_id import generate_run_id

logger = logging.getLogger(__name__)


class WorkflowService:
    """工作流编排服务。

    集成迭代评估回路：
    1. 初始化运行状态
    2. 执行工作流生成
    3. 执行结构化评估
    4. 由迭代控制器决策：通过 / 回流 / 终止
    5. 通过 PlatformDispatcher 持久化所有状态和工件（包含可选的 XMind 交付）
    """

    def __init__(
        self,
        settings: Settings,
        repository: FileRunRepository | None = None,
        llm_client: LLMClient | None = None,
        state_repository: RunStateRepository | None = None,
        iteration_controller: IterationController | None = None,
        platform_dispatcher: PlatformDispatcher | None = None,
        enable_xmind: bool = False,
        project_context_service: ProjectContextService | None = None,
        # ---- 模板驱动生成支持 ----
        template_service: Optional["TemplateService"] = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or FileRunRepository(settings.output_dir)
        self.state_repository = state_repository or RunStateRepository(settings.output_dir)
        self.iteration_controller = iteration_controller or IterationController(
            max_iterations=settings.max_iterations,
            pass_threshold=settings.evaluation_pass_threshold,
        )
        self._llm_client = llm_client
        self._workflow = None
        self._run_registry: dict[str, CaseGenerationRun] = {}

        # 初始化平台分发器
        if platform_dispatcher is not None:
            self.platform_dispatcher = platform_dispatcher
        else:
            # 使用工厂函数模式：每次 dispatch 时按 run_dir 动态创建 XMind Agent
            xmind_agent_factory = self._create_xmind_agent_factory() if enable_xmind else None
            self.platform_dispatcher = PlatformDispatcher(
                repository=self.repository,
                xmind_agent_factory=xmind_agent_factory,
            )

        self.project_context_service = project_context_service
        self.template_service = template_service

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        """创建并执行一次带迭代评估回路的用例生成任务。"""
        # 使用 UTC+8 日期时间格式生成 run_id，替代原先的 UUID
        run_id = generate_run_id(
            output_dir=Path(self.settings.output_dir),
            timezone=self.settings.timezone,
        )

        # 提取 project_id 用于后续上下文加载
        project_id = getattr(request, 'project_id', None)

        # 持久化请求
        self.repository.save(
            run_id, request.model_dump(mode="json", by_alias=True), "request.json"
        )

        # 初始化运行状态
        run_state = self.iteration_controller.initialize_state(run_id)
        self.state_repository.save_run_state(run_state)

        result: dict = {}
        try:
            result = self._execute_with_iteration(run_id, request, run_state)

            # 重新加载最新状态
            run_state = self.state_repository.load_run_state(run_id)

            checkpoints = result.get("checkpoints", [])
            checkpoint_count = len(checkpoints)

            run = CaseGenerationRun(
                run_id=run_id,
                status=run_state.status.value,
                input=request,
                parsed_document=result.get("parsed_document"),
                research_summary=result.get("research_output"),
                test_cases=result.get("test_cases", []),
                quality_report=result.get("quality_report", QualityReport()),
                checkpoint_count=checkpoint_count,
                iteration_summary=self._build_iteration_summary(run_state),
            )
        except Exception as exc:
            # 失败运行持久化：记录错误并保存状态
            run_state = self.iteration_controller.mark_error(run_state, exc)
            self.state_repository.save_run_state(run_state)
            self.state_repository.save_iteration_log(run_state)

            run = CaseGenerationRun(
                run_id=run_id,
                status="failed",
                input=request,
                error=ErrorInfo(code=exc.__class__.__name__, message=str(exc)),
                iteration_summary=self._build_iteration_summary(run_state),
            )

        run = self._persist_run_artifacts(run, result)
        self._run_registry[run_id] = run
        return run

    def get_run(self, run_id: str) -> CaseGenerationRun:
        """根据 run_id 查询运行结果。

        优先从内存缓存读取，其次从文件系统加载。
        支持读取失败运行的状态。
        """
        cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            return cached_run

        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRun.model_validate(run_payload)

        # 尝试补充迭代摘要信息
        if self.state_repository.run_state_exists(run_id):
            try:
                run_state = self.state_repository.load_run_state(run_id)
                run = run.model_copy(
                    update={"iteration_summary": self._build_iteration_summary(run_state)}
                )
            except Exception:
                pass  # 状态文件损坏时不阻断主流程

        self._run_registry[run_id] = run
        return run

    def _execute_with_iteration(
        self,
        run_id: str,
        request: CaseGenerationRequest,
        run_state,
    ) -> dict:
        """执行带迭代评估回路的工作流。

        流程：
        1. 执行一轮主流程生成
        2. 执行结构化评估
        3. 由迭代控制器判断：通过 -> 结束 / 不通过但可恢复 -> 回流 / 停止条件 -> 失败
        """
        workflow = self._get_workflow()
        result: dict = {}

        # ---- 模板驱动生成支持：加载模板数据 ----
        template_data: dict | None = None
        template_id = getattr(request, "template_id", None)
        if template_id and self.template_service:
            try:
                template_obj = self.template_service.get(template_id)
                if template_obj is not None:
                    template_data = template_obj.model_dump()
                    logger.info(
                        "已加载模板: id=%s, name=%s",
                        template_id,
                        template_obj.metadata.name,
                    )
                else:
                    logger.warning(
                        "模板未找到 (id=%s)，降级为无模板模式", template_id
                    )
            except Exception:
                logger.warning(
                    "模板加载失败 (id=%s)，降级为无模板模式",
                    template_id,
                    exc_info=True,
                )

        while True:
            # 更新状态为 running
            run_state.status = RunStatus.RUNNING
            self.state_repository.save_run_state(run_state)

            # 执行工作流
            workflow_input = {
                "run_id": run_id,
                "file_path": request.file_path,
                "language": request.language,
                "request": request,
                "model_config": request.llm_config,
                "iteration_index": run_state.iteration_index,
                "project_id": getattr(request, 'project_id', None) or "",
                # ---- 模板驱动生成支持 ----
                "template": template_data,
                "template_id": template_id,
            }

            # 如果是回流且之前有结果，保留部分中间结果
            if run_state.iteration_index > 0 and result:
                workflow_input = self._prepare_retry_input(
                    workflow_input, result, run_state
                )

            result = workflow.invoke(workflow_input)

            # 更新状态为 evaluating
            run_state.status = RunStatus.EVALUATING
            run_state.current_stage = RunStage.EVALUATION
            self.state_repository.save_run_state(run_state)

            # 执行结构化评估
            evaluation = evaluate(
                test_cases=result.get("test_cases", []),
                checkpoints=result.get("checkpoints", []),
                research_output=result.get("research_output"),
                previous_score=run_state.last_evaluation_score,
                # ---- 模板驱动生成支持：传递模板数据用于合规性评估 ----
                template_data=template_data,
            )

            # 持久化评估报告
            self.state_repository.save_evaluation_report(
                run_id, evaluation, run_state.iteration_index
            )

            # 由迭代控制器做出决策
            decision = self.iteration_controller.decide(run_state, evaluation)

            # 收集本轮工件快照
            artifacts_snapshot = {
                "test_case_count": str(len(result.get("test_cases", []))),
                "checkpoint_count": str(len(result.get("checkpoints", []))),
                "evaluation_score": str(evaluation.overall_score),
            }

            # 更新运行状态
            run_state = self.iteration_controller.update_state_after_evaluation(
                run_state, evaluation, decision, artifacts_snapshot
            )
            self.state_repository.save_run_state(run_state)
            self.state_repository.save_iteration_log(run_state)

            if decision.action in ("pass", "fail"):
                break

            # retry: 继续循环

        return result

    def _prepare_retry_input(
        self,
        workflow_input: dict,
        previous_result: dict,
        run_state,
    ) -> dict:
        """准备回流时的工作流输入。

        根据回流目标阶段，保留已有的上游结果：
        - 回到 context_research: 从头重跑
        - 回到 checkpoint_generation: 保留 parsed_document 和 research_output
        - 回到 draft_generation: 保留到 checkpoints 的所有中间结果
        """
        target = run_state.current_stage

        if target == RunStage.CONTEXT_RESEARCH:
            # 从头重跑，不保留
            return workflow_input

        if target == RunStage.CHECKPOINT_GENERATION:
            # 保留文档解析和研究输出
            if "parsed_document" in previous_result:
                workflow_input["parsed_document"] = previous_result["parsed_document"]
            if "research_output" in previous_result:
                workflow_input["research_output"] = previous_result["research_output"]
            return workflow_input

        # draft_generation 或其他: 保留尽可能多的中间结果
        for key in (
            "parsed_document",
            "research_output",
            "planned_scenarios",
            "checkpoints",
            "checkpoint_coverage",
            "mapped_evidence",
        ):
            if key in previous_result:
                workflow_input[key] = previous_result[key]

        return workflow_input

    def _build_iteration_summary(self, run_state) -> IterationSummary:
        """从运行状态构建轻量迭代摘要。"""
        return IterationSummary(
            iteration_count=len(run_state.iteration_history),
            last_evaluation_score=run_state.last_evaluation_score,
            had_retries=len(run_state.retry_decisions) > 0,
            final_stage=run_state.current_stage.value,
            retry_reasons=[d.retry_reason for d in run_state.retry_decisions],
        )

    def _get_workflow(self):
        """构建并缓存 LangGraph 工作流实例。

        当 ``project_context_service`` 可用时，使用
        ``build_project_context_loader`` 工厂函数创建闭包节点，
        而非直接调用节点函数。
        """
        if self._workflow is None:
            project_loader = None
            if self.project_context_service is not None:
                # 使用工厂函数创建闭包，而非直接执行节点函数
                project_loader = build_project_context_loader(
                    self.project_context_service
                )
            self._workflow = build_workflow(
                self._get_llm_client(),
                project_context_loader=project_loader,
            )
        return self._workflow

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            config = LLMClientConfig(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                model=self.settings.llm_model,
                timeout_seconds=self.settings.llm_timeout_seconds,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            self._llm_client = OpenAICompatibleLLMClient(config)
        return self._llm_client

    def _create_xmind_agent_factory(self):
        """创建 XMind 交付代理工厂函数。

        返回一个工厂函数，接受 run_dir 参数，
        每次调用时创建一个新的 XMindDeliveryAgent 实例，
        其 connector 输出目录指向指定的运行目录。
        """
        def factory(run_dir: Path) -> XMindDeliveryAgent:
            connector = FileXMindConnector(output_dir=run_dir)
            payload_builder = XMindPayloadBuilder()
            return XMindDeliveryAgent(
                connector=connector,
                payload_builder=payload_builder,
                output_dir=run_dir,
            )
        return factory

    def _persist_run_artifacts(
        self, run: CaseGenerationRun, workflow_result: dict | None = None
    ) -> CaseGenerationRun:
        """将运行结果的各项产物持久化到文件系统。

        通过 PlatformDispatcher 统一管理本地产物持久化和可选的 XMind 交付。
        """
        run_id = run.run_id
        wf = workflow_result or {}

        # 使用 PlatformDispatcher 进行产物持久化和平台交付
        artifacts = self.platform_dispatcher.dispatch(
            run_id=run_id,
            run=run,
            workflow_result=wf,
        )

        # 补充运行状态和评估报告路径
        run_state_path = self.state_repository._run_dir(run_id) / "run_state.json"
        if run_state_path.exists():
            artifacts["run_state"] = str(run_state_path)

        eval_path = self.state_repository._run_dir(run_id) / "evaluation_report.json"
        if eval_path.exists():
            artifacts["evaluation_report"] = str(eval_path)

        iter_log_path = self.state_repository._run_dir(run_id) / "iteration_log.json"
        if iter_log_path.exists():
            artifacts["iteration_log"] = str(iter_log_path)

        run_with_artifacts = run.model_copy(update={"artifacts": artifacts})
        run_result_path = self.repository.save(
            run_id,
            run_with_artifacts.model_dump(mode="json", by_alias=True),
            "run_result.json",
        )

        artifacts["run_result"] = str(run_result_path)
        final_run = run_with_artifacts.model_copy(update={"artifacts": artifacts})
        self.repository.save(
            run_id,
            final_run.model_dump(mode="json", by_alias=True),
            "run_result.json",
        )
        return final_run


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
