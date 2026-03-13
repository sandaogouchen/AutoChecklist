from __future__ import annotations

from uuid import uuid4

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRunResult, ErrorInfo
from app.graphs.main_workflow import build_workflow
from app.nodes.output_platform_writer import LocalPlatformPublisher, PlatformPublisher
from app.repositories.run_repository import FileRunRepository


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
        except Exception as exc:
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
            return cached_run

        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRunResult.model_validate(run_payload)
        self._run_registry[run_id] = run
        return run

    def _get_workflow(self):
        if self._workflow is None:
            self._workflow = build_workflow(
                self._get_llm_client(),
                repository=self.repository,
                platform_publisher=self._platform_publisher,
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
