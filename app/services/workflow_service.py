from __future__ import annotations

from uuid import uuid4

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun, ErrorInfo
from app.domain.case_models import QualityReport, TestCase
from app.graphs.main_workflow import build_workflow
from app.repositories.run_repository import FileRunRepository


class WorkflowService:
    def __init__(
        self,
        settings: Settings,
        repository: FileRunRepository | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or FileRunRepository(settings.output_dir)
        self._llm_client = llm_client
        self._workflow = None
        self._run_registry: dict[str, CaseGenerationRun] = {}

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        run_id = uuid4().hex
        self.repository.save(run_id, request.model_dump(mode="json", by_alias=True), "request.json")
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
            run = CaseGenerationRun(
                run_id=run_id,
                status="succeeded",
                input=request,
                parsed_document=result.get("parsed_document"),
                research_summary=result.get("research_output"),
                test_cases=result.get("test_cases", []),
                quality_report=result.get("quality_report", QualityReport()),
            )
        except Exception as exc:
            run = CaseGenerationRun(
                run_id=run_id,
                status="failed",
                input=request,
                error=ErrorInfo(code=exc.__class__.__name__, message=str(exc)),
            )

        run = self._persist_run_artifacts(run)
        self._run_registry[run_id] = run
        return run

    def get_run(self, run_id: str) -> CaseGenerationRun:
        cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            return cached_run

        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRun.model_validate(run_payload)
        self._run_registry[run_id] = run
        return run

    def _get_workflow(self):
        if self._workflow is None:
            self._workflow = build_workflow(self._get_llm_client())
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

    def _persist_run_artifacts(self, run: CaseGenerationRun) -> CaseGenerationRun:
        artifacts: dict[str, str] = {}
        run_id = run.run_id

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
    if not test_cases:
        return "# Generated Test Cases\n\nNo test cases were generated.\n"

    lines = ["# Generated Test Cases", ""]
    for test_case in test_cases:
        lines.append(f"## {test_case.id} {test_case.title}")
        lines.append("")
        lines.append("### Preconditions")
        lines.extend([f"- {item}" for item in test_case.preconditions] or ["- None"])
        lines.append("")
        lines.append("### Steps")
        lines.extend([f"{index}. {step}" for index, step in enumerate(test_case.steps, start=1)] or ["1. None"])
        lines.append("")
        lines.append("### Expected Results")
        lines.extend([f"- {item}" for item in test_case.expected_results] or ["- None"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"
