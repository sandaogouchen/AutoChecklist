"""工作流编排服务。

作为 API 层与工作流引擎之间的协调者，负责：
- 创建运行任务并执行 LangGraph 工作流
- 管理迭代评估回路的生命周期
- 通过 PlatformDispatcher 持久化运行产物
- 持久化运行状态、评估报告和迭代日志
- 查询历史运行结果

变更：
- 移除模块级 _render_test_cases_markdown 函数（DRY 修复，使用 markdown_renderer）
- 移除 TestCase 导入（不再直接使用）
- 新增 template_file_path 传递到工作流输入
- 新增 knowledge_retrieval_node 集成：当启用知识检索且 GraphRAG 引擎就绪时，
  构建知识检索节点并传入 build_workflow()
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
from app.domain.case_models import QualityReport
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
    5. 通过 PlatformDispatcher 持久化所有状态和工件
    """

    def __init__(
        self,
        settings: Settings,
        repository: FileRunRepository | None = None,
        llm_client: LLMClient | None = None,
        state_repository: RunStateRepository | None = None,
        iteration_controller: IterationController | None = None,
        platform_dispatcher: PlatformDispatcher | None = None,
        enable_xmind: bool = True,
        project_context_service: ProjectContextService | None = None,
        graphrag_engine=None,
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
        self._graphrag_engine = graphrag_engine

        if platform_dispatcher is not None:
            self.platform_dispatcher = platform_dispatcher
        else:
            xmind_agent_factory = self._create_xmind_agent_factory() if enable_xmind else None
            self.platform_dispatcher = PlatformDispatcher(
                repository=self.repository,
                xmind_agent_factory=xmind_agent_factory,
            )

        self.project_context_service = project_context_service

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        """创建并执行一次带迭代评估回路的用例生成任务。"""
        run_id = generate_run_id(
            output_dir=Path(self.settings.output_dir),
            timezone=self.settings.timezone,
        )

        project_id = getattr(request, 'project_id', None)

        self.repository.save(
            run_id, request.model_dump(mode="json", by_alias=True), "request.json"
        )

        run_state = self.iteration_controller.initialize_state(run_id)
        self.state_repository.save_run_state(run_state)

        result: dict = {}
        try:
            result = self._execute_with_iteration(run_id, request, run_state)

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
        """根据 run_id 查询运行结果。"""
        cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            return cached_run

        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRun.model_validate(run_payload)

        if self.state_repository.run_state_exists(run_id):
            try:
                run_state = self.state_repository.load_run_state(run_id)
                run = run.model_copy(
                    update={"iteration_summary": self._build_iteration_summary(run_state)}
                )
            except Exception:
                pass

        self._run_registry[run_id] = run
        return run

    def _execute_with_iteration(
        self,
        run_id: str,
        request: CaseGenerationRequest,
        run_state,
    ) -> dict:
        """执行带迭代评估回路的工作流。

        变更：新增 template_file_path 传递到工作流输入。
        """
        workflow = self._get_workflow()
        result: dict = {}

        while True:
            run_state.status = RunStatus.RUNNING
            self.state_repository.save_run_state(run_state)

            workflow_input = {
                "run_id": run_id,
                "file_path": request.file_path,
                "language": request.language,
                "request": request,
                "model_config": request.llm_config,
                "iteration_index": run_state.iteration_index,
                "project_id": getattr(request, 'project_id', None) or "",
            }

            # ---- 传递模版文件路径 ----
            template_file_path = getattr(request, 'template_file_path', None)
            if template_file_path:
                workflow_input["template_file_path"] = template_file_path

            if run_state.iteration_index > 0 and result:
                workflow_input = self._prepare_retry_input(
                    workflow_input, result, run_state
                )

            result = workflow.invoke(workflow_input)

            run_state.status = RunStatus.EVALUATING
            run_state.current_stage = RunStage.EVALUATION
            self.state_repository.save_run_state(run_state)

            evaluation = evaluate(
                test_cases=result.get("test_cases", []),
                checkpoints=result.get("checkpoints", []),
                research_output=result.get("research_output"),
                previous_score=run_state.last_evaluation_score,
            )

            self.state_repository.save_evaluation_report(
                run_id, evaluation, run_state.iteration_index
            )

            decision = self.iteration_controller.decide(run_state, evaluation)

            artifacts_snapshot = {
                "test_case_count": str(len(result.get("test_cases", []))),
                "checkpoint_count": str(len(result.get("checkpoints", []))),
                "evaluation_score": str(evaluation.overall_score),
            }

            run_state = self.iteration_controller.update_state_after_evaluation(
                run_state, evaluation, decision, artifacts_snapshot
            )
            self.state_repository.save_run_state(run_state)
            self.state_repository.save_iteration_log(run_state)

            if decision.action in ("pass", "fail"):
                break

        return result

    def _prepare_retry_input(
        self,
        workflow_input: dict,
        previous_result: dict,
        run_state,
    ) -> dict:
        """准备回流时的工作流输入。"""
        target = run_state.current_stage

        if target == RunStage.CONTEXT_RESEARCH:
            return workflow_input

        if target == RunStage.CHECKPOINT_GENERATION:
            if "parsed_document" in previous_result:
                workflow_input["parsed_document"] = previous_result["parsed_document"]
            if "research_output" in previous_result:
                workflow_input["research_output"] = previous_result["research_output"]
            return workflow_input

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

        变更：新增 knowledge_retrieval_node 集成。
        当启用知识检索且 GraphRAG 引擎就绪时，构建知识检索节点
        并传入 build_workflow()，使其在 context_research 之前执行。
        """
        if self._workflow is None:
            project_loader = None
            if self.project_context_service is not None:
                project_loader = build_project_context_loader(
                    self.project_context_service
                )

            # ---- 构建知识检索节点（如果可用）----
            knowledge_node = None
            if (
                self.settings.enable_knowledge_retrieval
                and self._graphrag_engine is not None
            ):
                try:
                    from app.nodes.knowledge_retrieval import (
                        build_knowledge_retrieval_node,
                    )

                    if self._graphrag_engine.is_ready():
                        knowledge_node = build_knowledge_retrieval_node(
                            self._graphrag_engine,
                            self.settings,
                        )
                        logger.info("知识检索节点已构建并注入工作流")
                    else:
                        logger.warning(
                            "GraphRAG 引擎未就绪，知识检索节点未注入"
                        )
                except Exception:
                    logger.exception("构建知识检索节点失败，工作流将不包含知识检索")

            self._workflow = build_workflow(
                self._get_llm_client(),
                project_context_loader=project_loader,
                knowledge_retrieval_node=knowledge_node,
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
        """创建 XMind 交付代理工厂函数。"""
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
        """将运行结果的各项产物持久化到文件系统。"""
        run_id = run.run_id
        wf = workflow_result or {}

        artifacts = self.platform_dispatcher.dispatch(
            run_id=run_id,
            run=run,
            workflow_result=wf,
        )

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
