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

            # ... 后续的迭代评估逻辑 ...

            # 持久化结果
            # ...

            return {"run_id": run_id, "status": "completed", "result": result}

        except Exception as e:
            logger.exception("工作流执行失败: %s", e)
            run_state = self.iteration_controller.mark_error(run_state, e)
            self.run_state_repository.save_run_state(run_state)
            raise
