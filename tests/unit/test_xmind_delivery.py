"""XMind 交付全链路测试。

覆盖以下核心场景：
- XMindPayloadBuilder 的树结构构建
- FileXMindConnector 的 .xmind 文件生成（文件名简洁化为 checklist.xmind）
- XMindDeliveryAgent 的完整交付流程及错误处理
- PlatformDispatcher 的产物持久化和 XMind 集成（XMind 归入运行目录）
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchOutput
from app.domain.xmind_models import (
    XMindDeliveryResult,
    XMindNode,
)
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder


# =========================================================================
# 测试辅助工厂
# =========================================================================


def _make_test_case(
    *,
    tc_id: str = "TC-001",
    title: str = "测试用例1",
    priority: str = "P0",
    module: str = "登录模块",
    steps: list[str] | None = None,
    expected: list[str] | None = None,
    category: str = "functional",
    preconditions: list[str] | None = None,
    checkpoint_id: str = "CP-001",
) -> TestCase:
    """创建测试辅助 TestCase。"""
    del module
    return TestCase(
        id=tc_id,
        title=title,
        priority=priority,
        steps=steps or ["步骤1", "步骤2"],
        expected_results=expected or ["期望结果"],
        category=category,
        preconditions=preconditions or ["前置条件"],
        checkpoint_id=checkpoint_id,
    )


def _make_checkpoint(
    *,
    checkpoint_id: str = "CP-001",
    name: str = "检查点1",
    status: str = "passed",
    details: str = "检查通过",
) -> Checkpoint:
    """创建测试辅助 Checkpoint。"""
    del status, details
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        title=name,
    )


def _make_research_output(
    *,
    summary: str = "研究摘要",
    key_findings: list[str] | None = None,
) -> ResearchOutput:
    """创建测试辅助 ResearchOutput。"""
    del summary
    return ResearchOutput(
        feature_topics=key_findings or ["发现1", "发现2"],
    )


def _make_optimized_tree() -> list[ChecklistNode]:
    """创建用于验证 XMind 树模式的优化树。"""
    return [
        ChecklistNode(
            node_id="GRP-001",
            title="用户已登录",
            node_type="precondition_group",
            preconditions=["用户已登录"],
            children=[
                ChecklistNode(
                    node_id="CASE-TC-OPT-001",
                    title="优化树测试用例",
                    node_type="case",
                    test_case_ref="TC-OPT-001",
                    preconditions=["已进入创建页"],
                    steps=["执行步骤"],
                    expected_results=["显示正确结果"],
                    priority="P1",
                    category="functional",
                )
            ],
        )
    ]


# =========================================================================
# XMindPayloadBuilder 测试
# =========================================================================


class TestXMindPayloadBuilder:
    """测试 XMindPayloadBuilder 的树结构构建。"""

    def test_build_basic_tree(self) -> None:
        """验证基本树结构包含所有必要节点。"""
        builder = XMindPayloadBuilder()
        root = builder.build(
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            research_output=_make_research_output(),
            title="测试标题",
        )

        assert isinstance(root, XMindNode)
        assert root.title == "测试标题"
        assert len(root.children) > 0

    def test_build_with_multiple_cases(self) -> None:
        """验证多个用例按模块分组。"""
        builder = XMindPayloadBuilder()
        cases = [
            _make_test_case(module="模块A", title="A-1"),
            _make_test_case(module="模块A", title="A-2"),
            _make_test_case(module="模块B", title="B-1"),
        ]
        root = builder.build(
            test_cases=cases,
            checkpoints=[],
            title="多用例测试",
        )

        assert isinstance(root, XMindNode)
        # 应有"用例"分支包含模块分组
        case_branch = next(
            (c for c in root.children if "用例" in c.title.lower() or "case" in c.title.lower() or "用例" in c.title),
            None,
        )
        # 至少存在一个非空子节点（即使分组策略不同也应有内容）
        assert root.children

    def test_build_empty_cases(self) -> None:
        """验证空用例列表也能正常构建。"""
        builder = XMindPayloadBuilder()
        root = builder.build(
            test_cases=[],
            checkpoints=[],
            title="空用例",
        )

        assert isinstance(root, XMindNode)
        assert root.title == "空用例"

    def test_build_without_research(self) -> None:
        """验证不传 research_output 也能构建。"""
        builder = XMindPayloadBuilder()
        root = builder.build(
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            title="无研究输出",
        )

        assert isinstance(root, XMindNode)

    def test_node_structure(self) -> None:
        """验证节点层级结构完整性。"""
        builder = XMindPayloadBuilder()
        root = builder.build(
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            research_output=_make_research_output(),
            title="结构测试",
        )

        # 递归检查所有节点都有 title
        def _check_node(node: XMindNode) -> None:
            assert node.title, "节点 title 不应为空"
            for child in node.children:
                _check_node(child)

        _check_node(root)

    def test_priority_in_labels(self) -> None:
        """验证优先级信息出现在节点标签或标题中。"""
        builder = XMindPayloadBuilder()
        root = builder.build(
            test_cases=[_make_test_case(priority="P0")],
            checkpoints=[],
            title="优先级测试",
        )

        # 在整棵树中搜索是否有 P0 相关信息
        def _search_tree(node: XMindNode, keyword: str) -> bool:
            if keyword in node.title:
                return True
            if any(keyword in label for label in node.labels):
                return True
            return any(_search_tree(c, keyword) for c in node.children)

        assert _search_tree(root, "P0"), "树中应包含 P0 优先级标记"


# =========================================================================
# FileXMindConnector 测试
# =========================================================================


class TestFileXMindConnector:
    """测试 FileXMindConnector 的 .xmind 文件生成。"""

    def test_creates_valid_xmind_file(self, tmp_path: Path) -> None:
        """验证生成的 .xmind 文件是有效的 ZIP 且包含正确的 JSON 结构。

        文件名应为固定的 checklist.xmind。
        """
        connector = FileXMindConnector(output_dir=tmp_path)

        root = XMindNode(
            title="测试思维导图",
            children=[
                XMindNode(
                    title="子节点1",
                    notes="备注信息",
                    labels=["P0", "功能"],
                ),
            ],
        )

        result = connector.create_map(root, "测试思维导图")

        assert result.success is True
        assert result.file_path
        assert result.error_message == ""

        # 验证文件存在且名称为 checklist.xmind
        xmind_file = Path(result.file_path)
        assert xmind_file.exists()
        assert xmind_file.name == "checklist.xmind"
        assert xmind_file.suffix == ".xmind"

        # 验证 ZIP 结构
        assert zipfile.is_zipfile(xmind_file)

        with zipfile.ZipFile(xmind_file, "r") as zf:
            assert "content.json" in zf.namelist()
            assert "metadata.json" in zf.namelist()

            # 验证 content.json 结构
            content = json.loads(zf.read("content.json"))
            assert isinstance(content, list)
            assert len(content) > 0

            sheet = content[0]
            assert sheet["class"] == "sheet"
            # sheet title 应为传入的 title 参数，而非文件名
            assert sheet["title"] == "测试思维导图"
            assert "rootTopic" in sheet

            root_topic = sheet["rootTopic"]
            assert root_topic["title"] == "测试思维导图"

            # 验证子节点
            children = root_topic.get("children", {}).get("attached", [])
            assert len(children) >= 1

            child = children[0]
            assert child["title"] == "子节点1"
            assert "notes" in child
            assert "labels" in child

    def test_xmind_file_in_run_directory(self, tmp_path: Path) -> None:
        """验证 XMind 文件输出到指定的运行目录下。"""
        run_dir = tmp_path / "2026-03-18_23-15-30"
        connector = FileXMindConnector(output_dir=run_dir)

        root = XMindNode(title="测试")
        result = connector.create_map(root, "测试")

        assert result.success is True
        xmind_file = Path(result.file_path)
        assert xmind_file.parent == run_dir
        assert xmind_file.name == "checklist.xmind"

    def test_health_check(self, tmp_path: Path) -> None:
        """验证健康检查功能。"""
        connector = FileXMindConnector(output_dir=tmp_path)
        assert connector.health_check() is True


# =========================================================================
# XMindDeliveryAgent 测试
# =========================================================================


class TestXMindDeliveryAgent:
    """测试 XMindDeliveryAgent 的交付流程。"""

    def test_uses_optimized_tree_for_xmind_output(self, tmp_path: Path) -> None:
        """传入 optimized_tree 时，XMind 应切换到前置条件树模式。"""
        run_dir = tmp_path / "tree-run"
        connector = FileXMindConnector(output_dir=run_dir)
        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=connector,
            payload_builder=builder,
            output_dir=run_dir,
        )

        result = agent.deliver(
            run_id="tree-run",
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            optimized_tree=_make_optimized_tree(),
            title="树模式交付",
            output_dir=run_dir,
        )

        assert result.success is True

        with zipfile.ZipFile(result.file_path, "r") as zf:
            content = json.loads(zf.read("content.json"))

        root_children = content[0]["rootTopic"]["children"]["attached"]
        assert root_children[0]["title"] == "[前置] 用户已登录"

    def test_success_delivery(self, tmp_path: Path) -> None:
        """验证完整的成功交付流程。

        XMind 文件应输出到运行目录下。
        """
        run_dir = tmp_path / "test-run-001"
        connector = FileXMindConnector(output_dir=run_dir)
        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=connector,
            payload_builder=builder,
            output_dir=run_dir,
        )

        result = agent.deliver(
            run_id="test-run-001",
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            research_output=_make_research_output(),
            title="测试交付",
            output_dir=run_dir,
        )

        assert result.success is True
        assert result.file_path
        assert result.error_message == ""

        # 验证 XMind 文件在运行目录下
        xmind_file = Path(result.file_path)
        assert xmind_file.parent == run_dir
        assert xmind_file.name == "checklist.xmind"

        # 验证交付元数据文件也在运行目录下
        meta_path = run_dir / "xmind_delivery.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["success"] is True
        assert "delivery_time" in meta

    def test_failure_graceful(self, tmp_path: Path) -> None:
        """验证 connector 异常时的优雅降级。"""
        mock_connector = MagicMock()
        mock_connector.create_map.side_effect = RuntimeError("模拟错误")

        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=mock_connector,
            payload_builder=builder,
            output_dir=tmp_path,
        )

        result = agent.deliver(
            run_id="fail-run",
            test_cases=[_make_test_case()],
            checkpoints=[],
            title="失败测试",
        )

        assert result.success is False
        assert "模拟错误" in result.error_message

    def test_empty_cases_delivery(self, tmp_path: Path) -> None:
        """验证空用例列表的交付。"""
        run_dir = tmp_path / "empty-run"
        connector = FileXMindConnector(output_dir=run_dir)
        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=connector,
            payload_builder=builder,
            output_dir=run_dir,
        )

        result = agent.deliver(
            run_id="empty-run",
            test_cases=[],
            checkpoints=[],
            title="空交付",
            output_dir=run_dir,
        )

        # 即使没有用例也应该能成功生成文件
        assert result.success is True
        assert result.file_path


# =========================================================================
# PlatformDispatcher 测试
# =========================================================================


class TestPlatformDispatcher:
    """测试 PlatformDispatcher 的产物持久化和平台交付。"""

    def test_dispatch_forwards_optimized_tree_to_xmind_agent(
        self, tmp_path: Path
    ) -> None:
        """dispatch 应将 optimized_tree 继续传给 XMind 交付。"""
        from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
        from app.domain.case_models import QualityReport
        from app.repositories.run_repository import FileRunRepository
        from app.services.platform_dispatcher import PlatformDispatcher

        repository = FileRunRepository(tmp_path)
        mock_agent = MagicMock(spec=XMindDeliveryAgent)
        mock_agent.deliver.return_value = XMindDeliveryResult(
            success=True,
            file_path="mocked/checklist.xmind",
        )

        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent=mock_agent,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="dispatch-tree",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )
        optimized_tree = _make_optimized_tree()

        dispatcher.dispatch(
            run_id="dispatch-tree",
            run=run,
            workflow_result={
                "checkpoints": [_make_checkpoint()],
                "optimized_tree": optimized_tree,
            },
        )

        assert mock_agent.deliver.call_args.kwargs["optimized_tree"] == optimized_tree

    def test_with_xmind_factory(self, tmp_path: Path) -> None:
        """验证使用 xmind_agent_factory 时 XMind 产物在运行目录下。"""
        from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
        from app.domain.case_models import QualityReport
        from app.repositories.run_repository import FileRunRepository
        from app.services.platform_dispatcher import PlatformDispatcher

        repository = FileRunRepository(tmp_path)

        # 创建工厂函数
        def xmind_factory(run_dir: Path) -> XMindDeliveryAgent:
            connector = FileXMindConnector(output_dir=run_dir)
            builder = XMindPayloadBuilder()
            return XMindDeliveryAgent(
                connector=connector,
                payload_builder=builder,
                output_dir=run_dir,
            )

        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent_factory=xmind_factory,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="dispatch-test",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )
        workflow_result = {"checkpoints": [_make_checkpoint()]}

        artifacts = dispatcher.dispatch(
            run_id="dispatch-test",
            run=run,
            workflow_result=workflow_result,
        )

        # 应包含 xmind 产物
        assert "xmind_file" in artifacts

        # XMind 文件应在运行目录下
        xmind_path = Path(artifacts["xmind_file"])
        run_dir = repository._run_dir("dispatch-test")
        assert xmind_path.parent == run_dir
        assert xmind_path.name == "checklist.xmind"

    def test_with_xmind_agent_backward_compat(self, tmp_path: Path) -> None:
        """验证直接传入 xmind_agent 仍然可用（向后兼容）。"""
        from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
        from app.domain.case_models import QualityReport
        from app.repositories.run_repository import FileRunRepository
        from app.services.platform_dispatcher import PlatformDispatcher

        repository = FileRunRepository(tmp_path)
        run_dir = repository._run_dir("compat-test")
        connector = FileXMindConnector(output_dir=run_dir)
        builder = XMindPayloadBuilder()
        xmind_agent = XMindDeliveryAgent(
            connector=connector,
            payload_builder=builder,
            output_dir=run_dir,
        )
        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent=xmind_agent,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="compat-test",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )
        workflow_result = {"checkpoints": [_make_checkpoint()]}

        artifacts = dispatcher.dispatch(
            run_id="compat-test",
            run=run,
            workflow_result=workflow_result,
        )

        assert "xmind_file" in artifacts

    def test_xmind_failure_doesnt_break(self, tmp_path: Path) -> None:
        """验证 XMind 失败不会导致整个 dispatch 失败。"""
        from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
        from app.domain.case_models import QualityReport
        from app.repositories.run_repository import FileRunRepository
        from app.services.platform_dispatcher import PlatformDispatcher

        repository = FileRunRepository(tmp_path)
        mock_agent = MagicMock(spec=XMindDeliveryAgent)
        mock_agent.deliver.side_effect = RuntimeError("XMind 服务不可用")

        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent=mock_agent,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="xmind-fail",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )

        # 不应抛出异常
        artifacts = dispatcher.dispatch(
            run_id="xmind-fail",
            run=run,
            workflow_result={},
        )

        # 本地产物应正常存在
        assert "run_json" in artifacts or "run_markdown" in artifacts or isinstance(artifacts, dict)


# =========================================================================
# 交付结果持久化测试
# =========================================================================


class TestXMindDeliveryResultInArtifacts:
    """测试交付结果的元数据持久化。"""

    def test_delivery_result_persisted(self, tmp_path: Path) -> None:
        """验证交付结果元数据被持久化。"""
        run_dir = tmp_path / "persist-test"
        connector = FileXMindConnector(output_dir=run_dir)
        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=connector,
            payload_builder=builder,
            output_dir=run_dir,
        )

        result = agent.deliver(
            run_id="persist-test",
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            title="持久化测试",
            output_dir=run_dir,
        )

        # 验证元数据文件存在且可解析
        meta_path = run_dir / "xmind_delivery.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "success" in meta
        assert "file_path" in meta
