"""知识检索工作流集成测试。

测试知识检索节点在 LangGraph 工作流中的集成：
- 工作流图正确包含 knowledge_retrieval 节点
- 知识检索节点不影响工作流整体运行
- 功能关闭时工作流正常运行（无知识检索节点）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.graphs.main_workflow import build_workflow


class TestWorkflowWithKnowledgeRetrieval:
    """知识检索节点在工作流中的集成测试。"""

    def test_workflow_builds_without_knowledge_node(self, fake_llm_client) -> None:
        """不提供知识检索节点时，工作流应正常构建。"""
        workflow = build_workflow(fake_llm_client)
        assert workflow is not None

    def test_workflow_builds_with_knowledge_node(self, fake_llm_client) -> None:
        """提供知识检索节点时，工作流应正常构建。"""

        def mock_knowledge_node(state: dict) -> dict:
            return {
                "knowledge_context": "模拟知识上下文",
                "knowledge_sources": ["doc_test"],
                "knowledge_retrieval_success": True,
            }

        workflow = build_workflow(
            fake_llm_client,
            knowledge_retrieval_node=mock_knowledge_node,
        )
        assert workflow is not None

    def test_workflow_builds_with_both_optional_nodes(self, fake_llm_client) -> None:
        """同时提供 project_context_loader 和 knowledge_retrieval_node 时应正常构建。"""

        def mock_project_loader(state: dict) -> dict:
            return {"project_context_summary": "项目上下文"}

        def mock_knowledge_node(state: dict) -> dict:
            return {
                "knowledge_context": "知识上下文",
                "knowledge_sources": [],
                "knowledge_retrieval_success": True,
            }

        workflow = build_workflow(
            fake_llm_client,
            project_context_loader=mock_project_loader,
            knowledge_retrieval_node=mock_knowledge_node,
        )
        assert workflow is not None


class TestWorkflowServiceKnowledgeIntegration:
    """WorkflowService 与知识检索引擎集成测试。"""

    def test_workflow_service_accepts_graphrag_engine(self) -> None:
        """WorkflowService 应接受 graphrag_engine 参数。"""
        from app.services.workflow_service import WorkflowService

        settings = MagicMock()
        settings.output_dir = "/tmp/test_output"
        settings.max_iterations = 1
        settings.evaluation_pass_threshold = 0.7
        settings.timezone = "UTC"
        settings.enable_knowledge_retrieval = True

        mock_engine = MagicMock()
        mock_engine.is_ready.return_value = True

        # 不应抛异常
        service = WorkflowService(
            settings=settings,
            graphrag_engine=mock_engine,
            enable_xmind=False,
        )
        assert service._graphrag_engine is mock_engine

    def test_workflow_service_without_engine(self) -> None:
        """不传 graphrag_engine 时 WorkflowService 应正常创建。"""
        from app.services.workflow_service import WorkflowService

        settings = MagicMock()
        settings.output_dir = "/tmp/test_output"
        settings.max_iterations = 1
        settings.evaluation_pass_threshold = 0.7
        settings.timezone = "UTC"
        settings.enable_knowledge_retrieval = False

        service = WorkflowService(
            settings=settings,
            enable_xmind=False,
        )
        assert service._graphrag_engine is None
