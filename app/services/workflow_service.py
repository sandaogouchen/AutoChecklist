from __future__ import annotations

import logging
from uuid import uuid4

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRunResult, ErrorInfo
from app.graphs.main_workflow import build_workflow
from app.nodes.output_platform_writer import LocalPlatformPublisher, PlatformPublisher
from app.repositories.run_repository import FileRunRepository

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(
        self,
        settings: Settings,
        repository: FileRunRepository | None = None,
        llm_client: LLMClient | None = None,
        platform_publisher: PlatformPublisher | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or FileRunRepository(settings.output_dir)
        self._llm_client = llm_client
        self._platform_publisher = platform_publisher or LocalPlatformPublisher(self.repository.root_dir)
        self._workflow = None
        self._run_registry: dict[str, CaseGenerationRunResult] = {}

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRunResult:
        run_id = uuid4().hex
        logger.info(
            "开始执行用例生成流程：run_id=%s, file_path=%s, language=%s",
            run_id,
            request.file_path,
            request.language,
        )
        try:
            result = self._get_workflow().invoke(
                {
                    "run_id": run_id,
                    "file_path": request.file_path,
                    "language": request.language,
                    "request": request,
                    "model_config": request.llm_config,
                }
            )
            run = CaseGenerationRunResult(
                run_id=run_id,
                status="succeeded",
                result=result["output_summary"],
            )
            logger.info(
                "用例生成流程执行成功：run_id=%s, test_case_count=%s, warning_count=%s",
                run_id,
                run.result.test_case_count if run.result is not None else 0,
                run.result.warning_count if run.result is not None else 0,
            )
        except Exception as exc:
            logger.exception("用例生成流程执行失败：run_id=%s, error=%s", run_id, exc)
            run = CaseGenerationRunResult(
                run_id=run_id,
                status="failed",
                error=ErrorInfo(code=exc.__class__.__name__, message=str(exc)),
            )

        self._run_registry[run_id] = run
        return run

    def get_run(self, run_id: str) -> CaseGenerationRunResult:
        cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            logger.info("命中运行结果缓存：run_id=%s, status=%s", run_id, cached_run.status)
            return cached_run

        logger.info("从磁盘加载运行结果：run_id=%s", run_id)
        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRunResult.model_validate(run_payload)
        self._run_registry[run_id] = run
        return run

    def _get_workflow(self):
        if self._workflow is None:
            logger.info("初始化工作流实例。")
            self._workflow = build_workflow(
                self._get_llm_client(),
                repository=self.repository,
                platform_publisher=self._platform_publisher,
            )
        return self._workflow

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            logger.info("初始化 LLM 客户端：base_url=%s, model=%s", self.settings.llm_base_url, self.settings.llm_model)
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
