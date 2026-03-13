from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.api_models import CaseGenerationRunResult
from app.domain.output_models import OutputArtifact, OutputBundle, OutputSummary
from app.domain.state import GlobalState
from app.repositories.run_repository import FileRunRepository
from app.utils.filesystem import ensure_directory, write_json


class PlatformPublisher(Protocol):
    def publish(self, run_id: str, bundle: OutputBundle) -> OutputArtifact:
        ...


class LocalPlatformPublisher:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def publish(self, run_id: str, bundle: OutputBundle) -> OutputArtifact:
        ensure_directory(self.root_dir)
        target_path = self.root_dir / f"{run_id}-platform.json"
        write_json(
            target_path,
            {
                "run_id": run_id,
                "test_case_count": bundle.test_case_count,
                "warning_count": bundle.warning_count,
                "artifacts": sorted(bundle.file_payloads.keys()),
            },
        )
        return OutputArtifact(
            key="platform_delivery",
            path=str(target_path),
            kind="platform",
            format="json",
        )


def build_output_platform_writer_node(
    publisher: PlatformPublisher,
    repository: FileRunRepository | None = None,
):
    def output_platform_writer_node(state: GlobalState) -> GlobalState:
        output = publisher.publish(state["run_id"], state["output_bundle"])
        outputs = [*state.get("outputs", []), output]
        bundle = state["output_bundle"]
        artifacts = dict(state.get("artifacts", {}))
        if repository is not None:
            run_result_path = repository.artifact_path(state["run_id"], "run_result.json")
            artifacts["run_result"] = str(run_result_path)
        summary = OutputSummary(
            run_id=state["run_id"],
            status="succeeded",
            test_case_count=bundle.test_case_count,
            warning_count=bundle.warning_count,
            artifacts=artifacts,
            outputs=outputs,
        )
        if repository is not None:
            repository.save(
                state["run_id"],
                CaseGenerationRunResult(
                    run_id=state["run_id"],
                    status="succeeded",
                    result=summary,
                ).model_dump(mode="json", by_alias=True, exclude_none=True),
                "run_result.json",
            )
        return {
            "outputs": outputs,
            "artifacts": artifacts,
            "output_summary": summary,
        }

    return output_platform_writer_node
