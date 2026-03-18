"""XMind 交付代理。

封装 XMind 思维导图的构建和交付流程，提供防御性的错误处理——
任何内部异常都不会向上传播，而是通过 ``XMindDeliveryResult`` 返回错误信息。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.xmind_models import XMindDeliveryResult, XMindNode
from app.services.xmind_connector import XMindConnector
from app.services.xmind_payload_builder import XMindPayloadBuilder

if TYPE_CHECKING:
    from app.domain.case_models import TestCase
    from app.domain.checkpoint_models import Checkpoint
    from app.domain.research_models import ResearchOutput

logger = logging.getLogger(__name__)


class XMindDeliveryAgent:
    """XMind 交付代理。

    编排 XMind 载荷构建和文件生成的完整流程：
    1. 使用 ``XMindPayloadBuilder`` 将测试数据映射为节点树
    2. 使用 ``XMindConnector`` 将节点树序列化为 .xmind 文件
    3. 保存交付结果元数据（xmind_delivery.json）

    所有异常均被内部捕获，确保 XMind 交付失败不会影响主流程。
    """

    def __init__(
        self,
        connector: XMindConnector,
        payload_builder: XMindPayloadBuilder,
        output_dir: str | Path,
    ) -> None:
        """初始化交付代理。

        Args:
            connector: XMind 连接器实例。
            payload_builder: 载荷构建器实例。
            output_dir: 交付结果元数据的输出目录。
        """
        self.connector = connector
        self.payload_builder = payload_builder
        self.output_dir = Path(output_dir)

    def deliver(
        self,
        run_id: str,
        test_cases: list[TestCase],
        checkpoints: list[Checkpoint],
        research_output: ResearchOutput | None = None,
        title: str = "",
        output_dir: str | Path | None = None,
    ) -> XMindDeliveryResult:
        """执行 XMind 交付流程。

        构建思维导图节点树，生成 .xmind 文件，并保存交付元数据。
        该方法绝不会抛出异常——所有错误均通过返回值传递。

        Args:
            run_id: 运行 ID，用于关联交付产物。
            test_cases: 测试用例列表。
            checkpoints: 检查点列表。
            research_output: 研究输出（可选）。
            title: 思维导图标题。
            output_dir: 可选的运行级别输出目录。传入时 XMind 文件将
                输出到该目录下，而非 connector 的默认目录。

        Returns:
            交付结果对象。
        """
        try:
            # 如果指定了 run 级别的输出目录，动态更新 connector 的输出目录
            if output_dir is not None:
                run_output_dir = Path(output_dir)
                from app.services.xmind_connector import FileXMindConnector
                if isinstance(self.connector, FileXMindConnector):
                    self.connector.output_dir = run_output_dir
                    self.connector.output_dir.mkdir(parents=True, exist_ok=True)

            # 构建节点树
            root_node: XMindNode = self.payload_builder.build(
                test_cases=test_cases,
                checkpoints=checkpoints,
                research_output=research_output,
                run_id=run_id,
                title=title,
            )

            # 生成 .xmind 文件
            result: XMindDeliveryResult = self.connector.create_map(
                root_node=root_node,
                title=title or f"测试用例 - {run_id}",
            )

            # 更新交付时间
            result = result.model_copy(
                update={"delivery_time": datetime.now().isoformat()}
            )

            # 保存交付元数据到运行目录
            effective_output_dir = Path(output_dir) if output_dir else self.output_dir
            self._save_delivery_artifact(run_id, result, effective_output_dir)

            logger.info(
                "XMind 交付完成: run_id=%s, success=%s, file=%s",
                run_id,
                result.success,
                result.file_path,
            )
            return result

        except Exception as exc:
            logger.exception("XMind 交付过程发生异常: run_id=%s, error=%s", run_id, exc)
            error_result = XMindDeliveryResult(
                success=False,
                error_message=f"XMind 交付失败: {exc}",
                delivery_time=datetime.now().isoformat(),
            )
            # 尽力保存错误元数据
            try:
                effective_output_dir = Path(output_dir) if output_dir else self.output_dir
                self._save_delivery_artifact(run_id, error_result, effective_output_dir)
            except Exception:
                logger.warning("保存 XMind 交付错误元数据失败: run_id=%s", run_id)
            return error_result

    def _save_delivery_artifact(
        self,
        run_id: str,
        result: XMindDeliveryResult,
        base_dir: Path | None = None,
    ) -> None:
        """保存交付结果元数据到文件系统。

        Args:
            run_id: 运行 ID。
            result: 交付结果对象。
            base_dir: 元数据输出的基础目录。如果为 None，使用 self.output_dir。
        """
        effective_dir = base_dir if base_dir is not None else self.output_dir

        # 当 base_dir 即为 run 级别目录时，直接在其下写入；
        # 否则按旧逻辑在 base_dir / run_id 下写入。
        # 判断依据：如果 effective_dir 的最后一级路径就是 run_id，则直接使用
        if effective_dir.name == run_id:
            run_dir = effective_dir
        else:
            run_dir = effective_dir / run_id

        run_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = run_dir / "xmind_delivery.json"
        artifact_path.write_text(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
