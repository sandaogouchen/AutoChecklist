"""XMind 交付功能的单元测试。

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
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import EvidenceRef, ResearchFact, ResearchOutput
from app.domain.xmind_models import XMindDeliveryResult, XMindNode
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder


# ---------------------------------------------------------------------------
# 测试辅助数据
# ---------------------------------------------------------------------------


def _make_checkpoint(
    checkpoint_id: str = "CP-test0001",
    title: str = "验证短信登录成功流程",
    fact_ids: list[str] | None = None,
    category: str = "functional",
    risk: str = "high",
) -> Checkpoint:
    """创建测试用 Checkpoint 实例。"""
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        title=title,
        objective="用户可以使用有效短信验证码成功登录",
        category=category,
        risk=risk,
        fact_ids=fact_ids or ["FACT-001"],
        evidence_refs=[
            EvidenceRef(
                section_title="Login Feature",
                excerpt="SMS-based login flow",
                line_start=3,
                line_end=6,
                confidence=0.9,
            )
        ],
        preconditions=["用户已注册手机号"],
    )


def _make_test_case(
    case_id: str = "TC-001",
    title: str = "用户使用短信验证码登录",
    checkpoint_id: str = "CP-test0001",
    priority: str = "P1",
) -> TestCase:
    """创建测试用 TestCase 实例。"""
    return TestCase(
        id=case_id,
        title=title,
        preconditions=["用户已注册手机号"],
        steps=["打开登录页面", "请求短信验证码", "提交有效验证码"],
        expected_results=["用户进入仪表盘"],
        priority=priority,
        category="functional",
        checkpoint_id=checkpoint_id,
        evidence_refs=[
            EvidenceRef(
                section_title="Acceptance Criteria",
                excerpt="Successful login redirects to the dashboard.",
                line_start=7,
                line_end=10,
                confidence=0.9,
            )
        ],
    )


def _make_research_output() -> ResearchOutput:
    """创建测试用 ResearchOutput 实例。"""
    return ResearchOutput(
        feature_topics=["Login"],
        user_scenarios=["用户使用短信验证码登录"],
        constraints=["短信验证码5分钟过期"],
        facts=[
            ResearchFact(
                fact_id="FACT-001",
                description="用户可以使用短信验证码登录",
                source_section="Login Feature",
                category="behavior",
            ),
            ResearchFact(
                fact_id="FACT-002",
                description="短信验证码5分钟过期",
                source_section="Acceptance Criteria",
                category="constraint",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# XMindPayloadBuilder 测试
# ---------------------------------------------------------------------------


class TestXMindPayloadBuilder:
    """测试 XMindPayloadBuilder 的树结构构建。"""

    def test_basic_tree_structure(self) -> None:
        """验证基本的节点树结构。"""
        builder = XMindPayloadBuilder()
        checkpoint = _make_checkpoint()
        test_case = _make_test_case()
        research_output = _make_research_output()

        root = builder.build(
            test_cases=[test_case],
            checkpoints=[checkpoint],
            research_output=research_output,
            run_id="test-run-001",
            title="测试用例集",
        )

        assert root.title == "测试用例集"
        # 应有至少一个一级子节点（checkpoint 分组）
        assert len(root.children) >= 1

        # 第一个子节点应是 checkpoint 分组
        cp_node = root.children[0]
        assert "CP-test0001" in cp_node.title

        # checkpoint 下应有测试用例
        assert len(cp_node.children) >= 1
        case_node = cp_node.children[0]
        assert "TC-001" in case_node.title

    def test_empty_input(self) -> None:
        """验证空输入时的处理。"""
        builder = XMindPayloadBuilder()

        root = builder.build(
            test_cases=[],
            checkpoints=[],
            research_output=None,
            run_id="empty-run",
        )

        assert root.title  # 根节点标题不为空
        assert len(root.children) == 0

    def test_ungrouped_cases(self) -> None:
        """验证未关联 checkpoint 的用例被归入「其他用例」分组。"""
        builder = XMindPayloadBuilder()
        test_case = _make_test_case(checkpoint_id="")

        root = builder.build(
            test_cases=[test_case],
            checkpoints=[],
        )

        assert len(root.children) == 1
        assert root.children[0].title == "其他用例"

    def test_uncovered_facts_node(self) -> None:
        """验证未覆盖的事实被添加为提示节点。"""
        builder = XMindPayloadBuilder()
        research_output = _make_research_output()
        # 只有一个 checkpoint 覆盖 FACT-001，FACT-002 未覆盖
        checkpoint = _make_checkpoint(fact_ids=["FACT-001"])

        root = builder.build(
            test_cases=[_make_test_case()],
            checkpoints=[checkpoint],
            research_output=research_output,
        )

        # 应有一个「未覆盖的事实」节点
        titles = [c.title for c in root.children]
        uncovered_titles = [t for t in titles if "未覆盖" in t]
        assert len(uncovered_titles) == 1


# ---------------------------------------------------------------------------
# FileXMindConnector 测试
# ---------------------------------------------------------------------------


class TestFileXMindConnector:
    """测试 FileXMindConnector 的 .xmind 文件生成。"""

    def test_creates_valid_xmind_file(self, tmp_path: Path) -> None:
        """验证生成的 .xmind 文件是有效的 ZIP 且包含正确的 JSON 结构。

        文件名应为固定的 checklist.xmind。
        """
        connector = FileXMindConnector(output_dir=tmp_path)

        root = XMindNode(
            title="测试根节点",
            children=[
                XMindNode(
                    title="子节点1",
                    children=[XMindNode(title="叶子节点")],
                    markers=["star-blue"],
                    notes="测试备注",
                    labels=["P1"],
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
        with zipfile.ZipFile(xmind_file, "r") as zf:
            names = zf.namelist()
            assert "content.json" in names
            assert "metadata.json" in names
            assert "manifest.json" in names

            # 验证 content.json 结构
            content = json.loads(zf.read("content.json"))
            assert isinstance(content, list)
            assert len(content) == 1

            sheet = content[0]
            assert sheet["class"] == "sheet"
            # sheet title 应为传入的 title 参数，而非文件名
            assert sheet["title"] == "测试思维导图"
            assert "rootTopic" in sheet

            root_topic = sheet["rootTopic"]
            assert root_topic["title"] == "测试根节点"
            assert "children" in root_topic
            assert "attached" in root_topic["children"]

            # 验证子节点
            attached = root_topic["children"]["attached"]
            assert len(attached) == 1
            child = attached[0]
            assert child["title"] == "子节点1"
            assert "markers" in child
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


# ---------------------------------------------------------------------------
# XMindDeliveryAgent 测试
# ---------------------------------------------------------------------------


class TestXMindDeliveryAgent:
    """测试 XMindDeliveryAgent 的交付流程。"""

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

    def test_failure_graceful(self, tmp_path: Path) -> None:
        """验证连接器失败时不会抛出异常。"""
        # 使用 Mock 连接器模拟失败
        mock_connector = MagicMock()
        mock_connector.create_map.side_effect = RuntimeError("模拟连接失败")

        builder = XMindPayloadBuilder()
        agent = XMindDeliveryAgent(
            connector=mock_connector,
            payload_builder=builder,
            output_dir=tmp_path,
        )

        # 不应抛出异常
        result = agent.deliver(
            run_id="fail-run",
            test_cases=[_make_test_case()],
            checkpoints=[_make_checkpoint()],
            title="失败测试",
        )

        assert result.success is False
        assert "失败" in result.error_message or "模拟" in result.error_message

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


# ---------------------------------------------------------------------------
# PlatformDispatcher 测试
# ---------------------------------------------------------------------------


class TestPlatformDispatcher:
    """测试 PlatformDispatcher 的产物持久化和平台交付。"""

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

        # 应包含标准产物
        assert "test_cases" in artifacts
        assert "test_cases_markdown" in artifacts
        assert "quality_report" in artifacts

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
        fromapp.domain.case_models import QualityReport
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

        # 使用 Mock 代理模拟失败
        mock_xmind_agent = MagicMock()
        mock_xmind_agent.deliver.side_effect = RuntimeError("XMind 意外崩溃")

        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent=mock_xmind_agent,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="fail-dispatch",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )

        # 不应抛出异常
        artifacts = dispatcher.dispatch(
            run_id="fail-dispatch",
            run=run,
            workflow_result={},
        )

        # 标准产物应正常生成
        assert "test_cases" in artifacts
        assert "quality_report" in artifacts
        # xmind 产物不应存在
        assert "xmind_file" not in artifacts

    def test_without_xmind(self, tmp_path: Path) -> None:
        """验证未启用 XMind 时只有标准产物。"""
        from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
        from app.domain.case_models import QualityReport
        from app.repositories.run_repository import FileRunRepository
        from app.services.platform_dispatcher import PlatformDispatcher

        repository = FileRunRepository(tmp_path)
        dispatcher = PlatformDispatcher(
            repository=repository,
            xmind_agent=None,
        )

        request = CaseGenerationRequest(file_path="test.md")
        run = CaseGenerationRun(
            run_id="no-xmind",
            status="succeeded",
            input=request,
            test_cases=[_make_test_case()],
            quality_report=QualityReport(),
        )

        artifacts = dispatcher.dispatch(
            run_id="no-xmind",
            run=run,
            workflow_result={},
        )

        assert "test_cases" in artifacts
        assert "xmind_file" not in artifacts


class TestXMindDeliveryResultInArtifacts:
    """测试 XMind 交付结果出现在产物中。"""

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
        assert "delivery_time" in meta
        assert meta["success"] is True
