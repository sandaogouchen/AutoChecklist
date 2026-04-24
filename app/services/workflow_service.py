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
- 新增节点级计时基础设施集成：在 _execute_with_iteration 中创建 NodeTimer，
  包装所有节点记录耗时，并持久化 timing_report.json
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import CocoSettings, Settings, get_coco_settings
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
from app.nodes.xmind_reference_loader import build_xmind_reference_loader_node
from app.parsers.xmind_parser import XMindParser
from app.repositories.file_repository import FileRepository
from app.repositories.run_repository import FileRunRepository
from app.repositories.run_state_repository import RunStateRepository
from app.services.iteration_controller import IterationController
from app.services.file_service import FileService
from app.services.platform_dispatcher import PlatformDispatcher
from app.services.project_context_service import ProjectContextService
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder
from app.services.xmind_reference_analyzer import XMindReferenceAnalyzer
from app.services.xmind_reference_tree_converter import XMindReferenceTreeConverter
from app.utils.run_id import generate_run_id
from app.utils.timing import NodeTimer, log_timing_report

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
        file_service: FileService | None = None,
        graphrag_engine=None,
        coco_settings: CocoSettings | None = None,
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
        self._run_registry_lock = threading.Lock()
        self._background_threads: dict[str, threading.Thread] = {}
        self._graphrag_engine = graphrag_engine
        self._coco_settings = coco_settings or get_coco_settings()

        if platform_dispatcher is not None:
            self.platform_dispatcher = platform_dispatcher
        else:
            xmind_agent_factory = self._create_xmind_agent_factory() if enable_xmind else None
            self.platform_dispatcher = PlatformDispatcher(
                repository=self.repository,
                xmind_agent_factory=xmind_agent_factory,
            )

        self.project_context_service = project_context_service
        self.file_service = file_service or FileService(
            FileRepository(db_path=Path(settings.output_dir) / "files.sqlite3")
        )

    def submit_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        """异步提交一次用例生成任务。

        设计目标：
        - API 层可在提交后立即返回 run_id（不阻塞长耗时工作流）
        - 后台线程执行原有同步 create_run 逻辑并持久化 run_result.json
        """
        run_id = generate_run_id(
            output_dir=Path(self.settings.output_dir),
            timezone=self.settings.timezone,
        )

        # 提交阶段做轻量校验：确保引用的 file_id 均存在，保持原 422 行为。
        self._validate_request_files_exist(request)

        # 提交阶段即写入 request.json，便于异步执行期间可查询 input。
        self.repository.save(
            run_id, request.model_dump(mode="json", by_alias=True), "request.json"
        )

        # 初始化 run_state（此处先标记为 pending；后台实际开始执行时会更新为 running）。
        run_state = self.iteration_controller.initialize_state(run_id)
        try:
            run_state.status = RunStatus.PENDING
        except Exception:
            pass
        self.state_repository.save_run_state(run_state)

        submitted = CaseGenerationRun(
            run_id=run_id,
            status=run_state.status.value,
            input=request,
            iteration_summary=self._build_iteration_summary(run_state),
        )
        with self._run_registry_lock:
            self._run_registry[run_id] = submitted

        t = threading.Thread(
            target=self._run_in_background,
            args=(run_id, request),
            daemon=True,
            name=f"workflow-run-{run_id}",
        )
        with self._run_registry_lock:
            self._background_threads[run_id] = t
        t.start()
        return submitted

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        """创建并执行一次带迭代评估回路的用例生成任务（同步执行）。"""
        run_id = generate_run_id(
            output_dir=Path(self.settings.output_dir),
            timezone=self.settings.timezone,
        )

        return self._execute_run_with_id(run_id, request)

    def _run_in_background(self, run_id: str, request: CaseGenerationRequest) -> None:
        try:
            final_run = self._execute_run_with_id(run_id, request)
            with self._run_registry_lock:
                self._run_registry[run_id] = final_run
        except Exception as exc:  # pragma: no cover
            # 理论上 _execute_run_with_id 内部已兜底并转为 failed，这里仅做最后保障。
            logger.exception("后台执行 run 失败: run_id=%s, error=%s", run_id, exc)
        finally:
            # 避免后台线程登记表无限增长
            with self._run_registry_lock:
                self._background_threads.pop(run_id, None)

    def _execute_run_with_id(self, run_id: str, request: CaseGenerationRequest) -> CaseGenerationRun:
        """使用指定 run_id 执行一次完整 run（供同步/异步两种入口复用）。"""

        # 注意：runs 请求中引用的上传文件内容保存在 SQLite。
        # 这里仅在运行期将其 materialize 到临时目录，避免写入 output/runs/<run_id>/ 下。
        temp_input_dir: Path | None = None
        try:
            temp_input_dir = Path(tempfile.mkdtemp(prefix=f"autochecklist_input_{run_id}_"))
            resolved_files = self._resolve_request_files(
                run_id,
                request,
                input_dir=temp_input_dir,
            )

            self.repository.save(
                run_id, request.model_dump(mode="json", by_alias=True), "request.json"
            )

            run_state = self.iteration_controller.initialize_state(run_id)
            self.state_repository.save_run_state(run_state)

            result: dict = {}
            try:
                result = self._execute_with_iteration(run_id, request, run_state, resolved_files)

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
            with self._run_registry_lock:
                self._run_registry[run_id] = run
            return run
        finally:
            if temp_input_dir is not None:
                shutil.rmtree(temp_input_dir, ignore_errors=True)

    def get_run(self, run_id: str) -> CaseGenerationRun:
        """根据 run_id 查询运行结果。

        - 若 run_result.json 已生成，返回完整结果。
        - 若仍在执行中（只有 request.json/run_state.json），返回当前状态快照。
        """
        with self._run_registry_lock:
            cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            return cached_run

        try:
            run_payload = self.repository.load(run_id, "run_result.json")
            run = CaseGenerationRun.model_validate(run_payload)
        except FileNotFoundError:
            # 运行尚未完成：尝试用 request.json + run_state.json 拼装状态快照
            request_payload = self.repository.load(run_id, "request.json")
            req = CaseGenerationRequest.model_validate(request_payload)

            status = RunStatus.PENDING.value
            artifacts: dict[str, str] = {}
            summary = IterationSummary()
            if self.state_repository.run_state_exists(run_id):
                try:
                    run_state = self.state_repository.load_run_state(run_id)
                    status = run_state.status.value
                    summary = self._build_iteration_summary(run_state)
                except Exception:
                    pass

                # 仅在文件存在时回填 artifacts
                try:
                    run_state_path = self.state_repository._run_dir(run_id) / "run_state.json"
                    if run_state_path.exists():
                        artifacts["run_state"] = str(run_state_path)
                except Exception:
                    pass

            run = CaseGenerationRun(
                run_id=run_id,
                status=status,
                input=req,
                artifacts=artifacts,
                iteration_summary=summary,
            )
        else:
            if self.state_repository.run_state_exists(run_id):
                try:
                    run_state = self.state_repository.load_run_state(run_id)
                    run = run.model_copy(
                        update={"iteration_summary": self._build_iteration_summary(run_state)}
                    )
                except Exception:
                    pass

        with self._run_registry_lock:
            self._run_registry[run_id] = run
        return run

    def _validate_request_files_exist(self, request: CaseGenerationRequest) -> None:
        """校验请求中引用的 file_id 是否存在。

        仅用于 API 异步提交阶段做快速失败（422）。
        """
        if self.file_service is None:
            return

        # 主输入（兼容 file_ids）
        prd_ids = list(getattr(request, "file_ids", None) or [])
        if not prd_ids:
            prd_ids = [request.file_id]
        for fid in prd_ids:
            if self.file_service.get_file_content(fid) is None:
                raise FileNotFoundError(f"File not found: {fid}")

        for optional_fid in [
            getattr(request, "reference_xmind_file_id", None),
        ]:
            if optional_fid and self.file_service.get_file_content(optional_fid) is None:
                raise FileNotFoundError(f"File not found: {optional_fid}")

        template_file_id = getattr(request, "template_file_id", None)
        if template_file_id:
            if self.file_service.get_file_content(template_file_id) is None:
                raise FileNotFoundError(f"File not found: {template_file_id}")
            if not self.file_service.is_template_file(template_file_id):
                raise ValueError(f"Template file expected: {template_file_id}")

    def _execute_with_iteration(
        self,
        run_id: str,
        request: CaseGenerationRequest,
        run_state,
        resolved_files: dict[str, str | None],
    ) -> dict:
        """执行带迭代评估回路的工作流。

        变更：
        - 新增 template_file_path 传递到工作流输入。
        - 新增 NodeTimer 计时集成：每轮迭代构建带计时的工作流，
          记录每个节点和 evaluate 的耗时，最终持久化 timing_report.json。
        """
        timer = NodeTimer()
        result: dict = {}

        while True:
            run_state.status = RunStatus.RUNNING
            self.state_repository.save_run_state(run_state)

            # 每轮迭代构建带计时包装的工作流（不使用缓存）
            workflow = self._build_timed_workflow(
                timer, run_state.iteration_index,
            )

            workflow_input = self._build_workflow_input(
                run_id=run_id,
                request=request,
                iteration_index=run_state.iteration_index,
                resolved_files=resolved_files,
            )

            if run_state.iteration_index > 0 and result:
                workflow_input = self._prepare_retry_input(
                    workflow_input, result, run_state
                )

            # ---- 工作流执行（内部记录，不计入汇总指标）----
            wf_start = time.monotonic()
            result = workflow.invoke(workflow_input)
            wf_elapsed = time.monotonic() - wf_start
            timer.record(
                "__workflow_invoke__",
                wf_elapsed,
                is_llm_node=False,
                iteration_index=run_state.iteration_index,
                is_internal=True,
            )

            run_state.status = RunStatus.EVALUATING
            run_state.current_stage = RunStage.EVALUATION
            self.state_repository.save_run_state(run_state)

            # ---- 评估（带计时）----
            eval_start = time.monotonic()
            evaluation = evaluate(
                test_cases=result.get("test_cases", []),
                checkpoints=result.get("checkpoints", []),
                research_output=result.get("research_output"),
                previous_score=run_state.last_evaluation_score,
            )
            eval_elapsed = time.monotonic() - eval_start
            timer.record(
                "evaluation",
                eval_elapsed,
                is_llm_node=False,
                iteration_index=run_state.iteration_index,
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

        # ---- 输出耗时汇总报告 ----
        timing_dict = log_timing_report(timer, run_id=run_id)

        # ---- 持久化 timing_report.json ----
        try:
            self.repository.save(run_id, timing_dict, "timing_report.json")
            logger.info("Timing report saved for run %s", run_id)
        except Exception:
            logger.exception("Failed to save timing report for run %s", run_id)

        # ---- 写入 run_state.timestamps（含 iteration 索引避免覆盖）----
        try:
            for record in timer.get_all_records():
                key = f"node.{record.node_name}.iter{record.iteration_index}"
                run_state.timestamps[key] = f"{record.elapsed_seconds:.2f}s"
            self.state_repository.save_run_state(run_state)
        except Exception:
            logger.exception("Failed to update run_state timestamps for run %s", run_id)

        return result

    def _build_timed_workflow(self, timer: NodeTimer, iteration_index: int):
        """构建带计时包装的工作流（每轮迭代重新构建，不缓存）。"""
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
            except Exception:
                logger.exception("构建知识检索节点失败")

        # Build XMind reference loader node
        xmind_parser = XMindParser()
        xmind_analyzer = XMindReferenceAnalyzer()
        tree_converter = XMindReferenceTreeConverter()
        xmind_reference_loader_node = build_xmind_reference_loader_node(
            xmind_parser, xmind_analyzer, tree_converter,
        )

        return build_workflow(
            self._get_llm_client(),
            project_context_loader=project_loader,
            knowledge_retrieval_node=knowledge_node,
            xmind_reference_loader_node=xmind_reference_loader_node,
            timer=timer,
            iteration_index=iteration_index,
            coco_settings=self._coco_settings,
        )

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
        """构建并缓存 LangGraph 工作流实例（无计时，用于非迭代场景）。

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

            # Build XMind reference loader node
            xmind_parser = XMindParser()
            xmind_analyzer = XMindReferenceAnalyzer()
            tree_converter = XMindReferenceTreeConverter()
            xmind_reference_loader_node = build_xmind_reference_loader_node(xmind_parser, xmind_analyzer, tree_converter)

            self._workflow = build_workflow(
                self._get_llm_client(),
                project_context_loader=project_loader,
                knowledge_retrieval_node=knowledge_node,
                xmind_reference_loader_node=xmind_reference_loader_node,
                coco_settings=self._coco_settings,
            )
        return self._workflow

    def _build_workflow_input(
        self,
        run_id: str,
        request: CaseGenerationRequest,
        iteration_index: int,
        resolved_files: dict[str, str | None] | None = None,
    ) -> dict:
        """构建工作流输入，包含 MR/Coco 配置与运行目录。"""
        if resolved_files is None:
            prd_file_ids = list(getattr(request, "file_ids", None) or [])
            if not prd_file_ids:
                prd_file_ids = [request.file_id]
            resolved_files = {
                # 兼容：历史逻辑使用 file_path 单值
                "file_path": prd_file_ids[0],
                # 新增：支持多个 PRD（file_id 列表）
                "file_ids": prd_file_ids,
                "template_file_path": getattr(request, "template_file_id", None),
                "reference_xmind_path": getattr(request, "reference_xmind_file_id", None),
            }

        workflow_input = {
            "run_id": run_id,
            "run_output_dir": str(self.repository._run_dir(run_id)),
            "file_path": resolved_files["file_path"],
            "file_ids": resolved_files.get("file_ids") or [],
            "language": request.language,
            "request": request,
            "model_config": request.llm_config,
            "iteration_index": iteration_index,
            "project_id": getattr(request, "project_id", None) or "",
        }

        template_file_path = resolved_files.get("template_file_path")
        if template_file_path:
            workflow_input["template_file_path"] = template_file_path

        reference_xmind_path = resolved_files.get("reference_xmind_path")
        if reference_xmind_path:
            workflow_input["reference_xmind_path"] = reference_xmind_path

        frontend_mr = self._build_mr_source_configs(getattr(request, "frontend_mr", None))
        if frontend_mr is not None:
            workflow_input["frontend_mr_config"] = frontend_mr

        backend_mr = self._build_mr_source_configs(getattr(request, "backend_mr", None))
        if backend_mr is not None:
            workflow_input["backend_mr_config"] = backend_mr

        should_use_coco_cache = (
            any(
                (item and item.get("use_coco"))
                for config in (frontend_mr, backend_mr)
                for item in ((config if isinstance(config, list) else [config]) if config else [])
            )
            and not getattr(self.settings, "mira_use_for_code_analysis", False)
        )
        if should_use_coco_cache:
            cache_hit = self._find_matching_coco_cache_run(run_id, request)
            if cache_hit is not None:
                workflow_input["coco_cache_run_id"] = cache_hit["run_id"]
                workflow_input["coco_cache_dir"] = cache_hit["coco_dir"]
            elif not getattr(self._coco_settings, "coco_jwt_token", ""):
                raise RuntimeError("Coco 已启用，但 COCO_JWT_TOKEN 未配置")

        return workflow_input

    def _resolve_request_files(
        self,
        run_id: str,
        request: CaseGenerationRequest,
        *,
        input_dir: Path | None = None,
    ) -> dict[str, str | None]:
        if self.file_service is None:
            raise RuntimeError("FileService 未配置，无法解析文件 ID")

        # 默认行为：不将请求附件写入 run 输出目录。
        # 若调用方未显式传入，则回退为系统临时目录。
        if input_dir is None:
            input_dir = Path(tempfile.mkdtemp(prefix=f"autochecklist_input_{run_id}_"))

        prd_file_ids = list(getattr(request, "file_ids", None) or [])
        if not prd_file_ids:
            prd_file_ids = [request.file_id]

        prd_paths: list[Path] = []
        for idx, prd_file_id in enumerate(prd_file_ids, start=1):
            prd_paths.append(
                Path(
                    self.file_service.materialize_to_path(
                        prd_file_id,
                        target_dir=input_dir,
                        file_name_prefix=f"source_{idx}",
                    )
                )
            )

        # 将多个 PRD 按顺序拼接为一个输入文件，供后续解析节点使用
        merged_path = prd_paths[0]
        if len(prd_paths) > 1:
            separator = "\n\n---\n\n"
            merged_path = input_dir / "source_merged.md"
            merged_text = separator.join(
                p.read_text(encoding="utf-8", errors="ignore") for p in prd_paths
            )
            merged_path.write_text(merged_text, encoding="utf-8")

        return {
            # 兼容：历史逻辑使用 file_path 单值（解析节点只消费该字段）
            "file_path": str(merged_path),
            # 新增：支持多个 PRD（供后续调试/溯源）
            "file_paths": [str(p) for p in prd_paths],
            "file_ids": prd_file_ids,
            "template_file_path": str(
                self.file_service.materialize_to_path(
                    request.template_file_id,
                    target_dir=input_dir,
                    file_name_prefix="template",
                )
            ) if getattr(request, "template_file_id", None) else None,
            "reference_xmind_path": str(
                self.file_service.materialize_to_path(
                    request.reference_xmind_file_id,
                    target_dir=input_dir,
                    file_name_prefix="reference_xmind",
                )
            ) if getattr(request, "reference_xmind_file_id", None) else None,
        }

    def _find_matching_coco_cache_run(
        self,
        current_run_id: str,
        request: CaseGenerationRequest,
    ) -> dict[str, str] | None:
        """按完整 request.json 精确匹配可复用的历史 Coco 工件。"""
        root_dir = self.repository.root_dir
        if not root_dir.exists():
            return None

        expected_payload = request.model_dump(mode="json", by_alias=True)
        candidates: list[Path] = []

        for run_dir in root_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name == current_run_id:
                continue

            request_path = run_dir / "request.json"
            coco_dir = run_dir / "coco"
            if not request_path.exists() or not coco_dir.is_dir():
                continue
            if not any(coco_dir.iterdir()):
                continue

            try:
                payload = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if payload == expected_payload:
                candidates.append(run_dir)

        if not candidates:
            return None

        chosen = sorted(candidates, key=lambda path: path.name, reverse=True)[0]
        logger.info(
            "命中历史 Coco 缓存: current_run=%s cache_run=%s",
            current_run_id,
            chosen.name,
        )
        return {
            "run_id": chosen.name,
            "coco_dir": str(chosen / "coco"),
        }

    @staticmethod
    def _normalize_mr_codebase_fields(
        mr_url: str,
        git_url: str,
        branch: str,
    ) -> tuple[str, str]:
        """归一化 MR 代码仓信息，兼容 Bits 页面链接输入。"""
        normalized_git_url = (git_url or "").strip()
        normalized_branch = (branch or "").strip()

        tree_match = re.match(
            r"^https://bits\.bytedance\.net/code/([^/]+/[^/]+)/tree/([^/?#]+)$",
            normalized_git_url,
        )
        if tree_match:
            repo_path, branch_from_url = tree_match.groups()
            normalized_git_url = f"https://code.byted.org/{repo_path}.git"
            if not normalized_branch:
                normalized_branch = branch_from_url

        if not normalized_git_url:
            mr_match = re.match(
                r"^https://bits\.bytedance\.net/code/([^/]+/[^/]+)/merge_requests/\d+$",
                (mr_url or "").strip(),
            )
            if mr_match:
                normalized_git_url = f"https://code.byted.org/{mr_match.group(1)}.git"

        return normalized_git_url, normalized_branch

    @staticmethod
    def _build_mr_source_config(mr_request) -> dict | None:
        """将单个 API 层 MRRequestConfig 映射为子图可消费的 MRSourceConfig 字典。"""
        if mr_request is None:
            return None

        mr_url = getattr(mr_request, "mr_url", "")
        git_url = getattr(mr_request, "git_url", "")
        local_path = getattr(mr_request, "local_path", "")
        branch = getattr(mr_request, "branch", "")
        commit_sha = getattr(mr_request, "commit_sha", "")
        use_coco = bool(getattr(mr_request, "use_coco", False))

        git_url, branch = WorkflowService._normalize_mr_codebase_fields(
            mr_url=mr_url,
            git_url=git_url,
            branch=branch,
        )

        if not any((mr_url, git_url, local_path)):
            return None

        return {
            "mr_url": mr_url,
            "use_coco": use_coco,
            "codebase": {
                "git_url": git_url,
                "local_path": local_path,
                "branch": branch,
                "commit_sha": commit_sha,
            },
        }

    @staticmethod
    def _build_mr_source_configs(mr_request_list) -> list[dict] | None:
        """将 API 层 MRRequestConfig（可为列表/单值）映射为 MRSourceConfig 字典列表。"""
        if mr_request_list is None:
            return None

        # 兼容旧版：单个对象
        if not isinstance(mr_request_list, list):
            mr_request_list = [mr_request_list]

        configs: list[dict] = []
        for item in mr_request_list:
            cfg = WorkflowService._build_mr_source_config(item)
            if cfg is not None:
                configs.append(cfg)
        return configs or None

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            config = LLMClientConfig(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                model=self.settings.llm_model,
                use_coco_as_llm=self.settings.llm_use_coco_as_llm,
                use_mira_as_llm=self.settings.llm_use_mira_as_llm,
                coco_api_base_url=getattr(self._coco_settings, "coco_api_base_url", ""),
                coco_jwt_token=getattr(self._coco_settings, "coco_jwt_token", ""),
                coco_agent_name=getattr(self._coco_settings, "coco_agent_name", "sandbox"),
                mira_api_base_url=getattr(self.settings, "mira_api_base_url", ""),
                mira_jwt_token=getattr(self.settings, "mira_jwt_token", ""),
                mira_cookie=getattr(self.settings, "mira_cookie", ""),
                mira_client_version=getattr(self.settings, "mira_client_version", "autochecklist/0.1.0"),
                mira_use_for_code_analysis=getattr(self.settings, "mira_use_for_code_analysis", False),
                timezone=getattr(self.settings, "timezone", "Asia/Shanghai"),
                timeout_seconds=self.settings.llm_timeout_seconds,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            logger.info(
                "Initializing LLM client: backend=%s model=%s timeout=%.1fs timezone=%s mira_analysis=%s",
                "mira" if config.use_mira_as_llm else "coco" if config.use_coco_as_llm else "openai-compatible",
                config.model or "<default>",
                config.timeout_seconds,
                config.timezone,
                config.mira_use_for_code_analysis,
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

        # ---- 将最终 checklist.xmind 写入 SQLite 文件存储，并回填 file_id ----
        # 说明：XMind 文件仍会先落盘到 run 目录（由 XMindDeliveryAgent/FileXMindConnector 生成），
        # 这里将其作为“生成产物”写入 files.sqlite3 以便前端通过 file_id 下载。
        xmind_path = artifacts.get("xmind_file")
        xmind_file_id: str | None = None
        if xmind_path and self.file_service is not None:
            try:
                xmind_bytes = Path(xmind_path).read_bytes()
                stored = self.file_service.create_file(
                    file_name=f"{run_id}.xmind",
                    content=xmind_bytes,
                    content_type="application/vnd.xmind.workbook",
                    tags=["generated_artifact", f"run:{run_id}", "type:xmind"],
                )
                xmind_file_id = stored.file_id
                artifacts["xmind_file_id"] = xmind_file_id
            except Exception:
                logger.exception("写入 XMind 生成产物到 SQLite 失败: run_id=%s", run_id)

        run_state_path = self.state_repository._run_dir(run_id) / "run_state.json"
        if run_state_path.exists():
            artifacts["run_state"] = str(run_state_path)

        eval_path = self.state_repository._run_dir(run_id) / "evaluation_report.json"
        if eval_path.exists():
            artifacts["evaluation_report"] = str(eval_path)

        iter_log_path = self.state_repository._run_dir(run_id) / "iteration_log.json"
        if iter_log_path.exists():
            artifacts["iteration_log"] = str(iter_log_path)

        # ---- timing report 产物追加（通过 self.repository 路径一致性）----
        try:
            timing_path = Path(self.repository._run_dir(run_id)) / "timing_report.json"
            if timing_path.exists():
                artifacts["timing_report"] = str(timing_path)
        except Exception:
            pass

        run_dir = Path(self.repository._run_dir(run_id))
        for provider in ("coco", "mira"):
            artifact_dir = run_dir / provider
            if not artifact_dir.exists():
                continue
            for path in sorted(artifact_dir.rglob("*")):
                if path.is_file():
                    artifacts[f"{provider}::{path.relative_to(artifact_dir).as_posix()}"] = str(path)

        run_update: dict = {"artifacts": artifacts}
        if xmind_file_id:
            run_update["checklist_xmind_file_id"] = xmind_file_id
        run_with_artifacts = run.model_copy(update=run_update)
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
