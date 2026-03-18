"""核心工作流编排服务。"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from app.clients.llm import LLMClient
from app.domain.api_models import CaseGenerationRequest, GenerationOptions
from app.domain.run_state import RunStage, RunState, RunStatus
from app.graphs.main_workflow import build_main_graph
from app.repositories.run_repository import FileRunRepository
from app.repositories.run_state_repository import RunStateRepository
from app.services.iteration_controller import IterationController
from app.services.project_context_service import ProjectContextService
from app.services.template_service import TemplateService
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder
from app.utils.run_id import generate_run_id

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(
        self,
        llm_client: LLMClient,
        run_repository: FileRunRepository,
        run_state_repository: RunStateRepository,
        project_service: ProjectContextService,
        # ---- 模板驱动生成支持（可选，向后兼容） ----
        template_service: Optional[TemplateService] = None,
    ) -> None:
        self.llm_client = llm_client
        self.run_repository = run_repository
        self.run_state_repository = run_state_repository
        self.project_service = project_service
        self.template_service = template_service
        self.iteration_controller = IterationController()

    async def execute(self, request: CaseGenerationRequest) -> dict[str, Any]:
        """执行用例生成工作流。"""
        run_id = str(uuid.uuid4())
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

        try:
            # 读取文件内容
            file_path = Path(request.file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {request.file_path}")
            raw_input = file_path.read_text(encoding="utf-8")

            # 获取项目上下文（可选）
            project_context = None
            if request.project_id:
                project_context = self.project_service.get_context(request.project_id)

            # ---- 模板加载（可选） ----
            # 如果请求指定了 template_id 且模板服务可用，则加载模板。
            # 加载失败时降级为无模板模式，不阻断主流程。
            template_data: Optional[dict] = None
            template_id = getattr(request, "template_id", None)
            if template_id and self.template_service:
                try:
                    template_obj = self.template_service.get_template(template_id)
                    if template_obj is not None:
                        template_data = template_obj.model_dump()
                        logger.info("已加载模板: id=%s, name=%s", template_id, template_obj.name)
                    else:
                        logger.warning("模板未找到 (id=%s)，降级为无模板模式", template_id)
                except Exception:
                    logger.warning("模板加载失败 (id=%s)，降级为无模板模式", template_id, exc_info=True)

            # 构建初始状态
            options = request.options or GenerationOptions()
            initial_state = {
                "raw_input": raw_input,
                "file_path": request.file_path,
                "language": request.language,
                "project_context": project_context,
                "project_id": request.project_id,
                "llm_config": request.llm_config.model_dump() if request.llm_config else None,
                "iteration_index": 0,
                "max_iterations": options.max_iterations,
                # ---- 模板驱动生成支持 ----
                "template": template_data,
                "template_id": template_id,
            }

            # 构建并执行工作流
            graph = build_main_graph(self.llm_client)
            result = await graph.ainvoke(initial_state)
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

            # ... 后续的迭代评估逻辑 ...

            # 持久化结果
            # ...

            return {"run_id": run_id, "status": "completed", "result": result}

        except Exception as e:
            logger.exception("工作流执行失败: %s", e)
            run_state = self.iteration_controller.mark_error(run_state, e)
            self.run_state_repository.save_run_state(run_state)
            raise
