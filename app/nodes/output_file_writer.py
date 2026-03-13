from __future__ import annotations

from app.domain.output_models import OutputArtifact
from app.domain.state import GlobalState
from app.repositories.run_repository import FileRunRepository


def build_output_file_writer_node(repository: FileRunRepository):
    def output_file_writer_node(state: GlobalState) -> GlobalState:
        bundle = state["output_bundle"]
        artifacts = repository.save_bundle(state["run_id"], bundle)
        outputs = [
            OutputArtifact(
                key=payload.key,
                path=artifacts[payload.key],
                kind="file",
                format=payload.format,
            )
            for payload in bundle.file_payloads.values()
        ]
        return {
            "artifacts": artifacts,
            "outputs": [*state.get("outputs", []), *outputs],
        }

    return output_file_writer_node
