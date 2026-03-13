from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.domain.state import GlobalState
from app.nodes.output_bundle_builder import output_bundle_builder_node
from app.nodes.output_file_writer import build_output_file_writer_node
from app.nodes.output_platform_writer import (
    LocalPlatformPublisher,
    PlatformPublisher,
    build_output_platform_writer_node,
)
from app.repositories.run_repository import FileRunRepository


def build_output_delivery_subgraph(
    repository: FileRunRepository,
    platform_publisher: PlatformPublisher | None = None,
):
    builder = StateGraph(GlobalState)
    builder.add_node("output_bundle_builder", output_bundle_builder_node)
    builder.add_node("output_file_writer", build_output_file_writer_node(repository))
    builder.add_node(
        "output_platform_writer",
        build_output_platform_writer_node(
            platform_publisher or LocalPlatformPublisher(repository.root_dir),
            repository=repository,
        ),
    )
    builder.add_edge(START, "output_bundle_builder")
    builder.add_edge("output_bundle_builder", "output_file_writer")
    builder.add_edge("output_file_writer", "output_platform_writer")
    builder.add_edge("output_platform_writer", END)
    return builder.compile()
