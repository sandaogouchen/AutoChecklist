"""工作流编排服务。

作为 API 层与工作流引擎之间的协调者，负责：
- 创建运行任务并执行 LangGraph 工作流
- 持久化运行产物（JSON + Markdown）
- 查询历史运行结果
"""

from __future__ import annotations

from uuid import uuid4

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun, ErrorInfo
from app.domain.case_models import QualityReport, TestCase
from app.graphs.main_workflow import build_workflow
from app.repositories.run_repository import FileRunRepository


class WorkflowService:
    """工作流编排服务。

    管理用例生成任务的完整生命周期：创建 → 执行 → 持久化 → 查询。
    通过依赖注入支持自定义 repository 和 llm_client，方便测试。
    """

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
        # 内存缓存：避免对同一 run_id 重复读取文件系统
        self._run_registry: dict[str, CaseGenerationRun] = {}

    def create_run(self, request: CaseGenerationRequest) -> CaseGenerationRun:
        """创建并执行一次用例生成任务。

        流程：
        1. 生成唯一的 run_id
        2. 持久化原始请求
        3. 调用 LangGraph 工作流执行完整的用例生成流水线
        4. 将结果和产物持久化到文件系统
        5. 缓存并返回运行结果

        异常处理：工作流执行失败时不抛出异常，而是将错误信息
        封装到 ``CaseGenerationRun.error`` 中返回，状态标记为 "failed"。
        """
        run_id = uuid4().hex

        # 持久化原始请求，便于事后审计和重放
        self.repository.save(
            run_id, request.model_dump(mode="json", by_alias=True), "request.json"
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

        # 持久化所有产物并更新缓存
        run = self._persist_run_artifacts(run)
        self._run_registry[run_id] = run
        return run

    def get_run(self, run_id: str) -> CaseGenerationRun:
        """根据 run_id 查询运行结果。

        优先从内存缓存中读取，缓存未命中时从文件系统加载。

        Raises:
            FileNotFoundError: 指定的 run_id 不存在。
        """
        cached_run = self._run_registry.get(run_id)
        if cached_run is not None:
            return cached_run

        run_payload = self.repository.load(run_id, "run_result.json")
        run = CaseGenerationRun.model_validate(run_payload)
        self._run_registry[run_id] = run
        return run

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _get_workflow(self):
        """延迟初始化并缓存 LangGraph 工作流实例。"""
        if self._workflow is None:
            self._workflow = build_workflow(self._get_llm_client())
        return self._workflow

    def _get_llm_client(self) -> LLMClient:
        """延迟初始化并缓存 LLM 客户端实例。"""
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
        """将运行结果的各项产物持久化到文件系统。

        产物包括：
        - parsed_document.json  — 解析后的文档结构
        - research_output.json  — 上下文研究输出
        - test_cases.json       — 测试用例（JSON 格式）
        - test_cases.md         — 测试用例（Markdown 可读格式）
        - quality_report.json   — 质量报告
        - run_result.json       — 完整运行结果（含 artifacts 路径映射）

        Returns:
            更新了 ``artifacts`` 字段的运行结果对象。
        """
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

        # 先保存一次包含 artifacts 路径的完整结果
        run_with_artifacts = run.model_copy(update={"artifacts": artifacts})
        run_result_path = self.repository.save(
            run_id,
            run_with_artifacts.model_dump(mode="json", by_alias=True),
            "run_result.json",
        )

        # 将 run_result 自身的路径也加入 artifacts，再次保存最终版本
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

    输出格式：每个用例包含标题、前置条件、操作步骤和预期结果四个部分。
    """
    if not test_cases:
        return "# Generated Test Cases\n\nNo test cases were generated.\n"

    lines = ["# Generated Test Cases", ""]
    for test_case in test_cases:
        lines.append(f"## {test_case.id} {test_case.title}")
        lines.append("")
        lines.append("### Preconditions")
        lines.extend(
            [f"- {item}" for item in test_case.preconditions] or ["- None"]
        )
        lines.append("")
        lines.append("### Steps")
        lines.extend(
            [f"{i}. {step}" for i, step in enumerate(test_case.steps, start=1)]
            or ["1. None"]
        )
        lines.append("")
        lines.append("### Expected Results")
        lines.extend(
            [f"- {item}" for item in test_case.expected_results] or ["- None"]
        )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
