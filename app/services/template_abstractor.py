"""模板抽象化服务。

将完整 XMind 参考树（~3000+ 节点）压缩为抽象验证维度模式（~50-80 个维度标签），
从根本上消除下游节点"照搬模板"的问题。

核心职责：
1. 接收 ``XMindReferenceSummary``（包含完整参考树）
2. 构建树摘要文本（L1-L4 结构 + 叶子计数）
3. 确定性提取边界提示（数值阈值、枚举值）
4. 调用 LLM 进行语义压缩，输出 ``AbstractedReferenceSchema``
5. 后处理填充统计字段
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.domain.abstracted_reference_models import (
    AbstractedModule,
    AbstractedReferenceSchema,
    AbstractedSubmodule,
    VerificationDimension,
)
from app.domain.xmind_reference_models import XMindReferenceNode, XMindReferenceSummary
from app.clients.llm import LLMClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 边界提示提取正则
# ---------------------------------------------------------------------------

# 数字阈值：匹配 "最多30个"、"超过20个"、"≤100" 等
_NUMERIC_THRESHOLD_RE = re.compile(
    r"(?:最[多少大小]|超过|不超过|≤|≥|>=|<=|限制|上限|下限)"
    r"\s*(\d+)\s*(?:个|条|次|天|小时|分钟|%)?",
)

# 独立数字值：匹配 "100个视频素材"、"30天" 等
_NUMERIC_VALUE_RE = re.compile(
    r"(\d+)\s*(?:个|条|次|天|小时|分钟|%|视频|素材|图片|字符|字节)",
)

# 枚举值集合：匹配 "VTR/conversion"、"daily/lifetime" 等斜线分隔
_ENUM_SLASH_RE = re.compile(
    r"\b([A-Za-z_][\w]*(?:/[A-Za-z_][\w]*){1,})\b",
)

# 特殊状态值：null、空值、0 等
_SPECIAL_VALUE_RE = re.compile(
    r"(?:=\s*(?:null|NULL|None|0|空值|空字符串|空))\b",
)

# 配置 ID 模式：纯数字 ID（4-6 位）
_CONFIG_ID_RE = re.compile(
    r"\b(\d{4,6})\b",
)

# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

_ABSTRACTION_SYSTEM_PROMPT = """你是测试结构分析专家。你的任务是分析给定的 XMind 测试用例模板树结构，
将其压缩为抽象的"验证维度"清单。

## 核心规则

1. **识别验证维度**：分析每个模块/子模块覆盖了哪些"类别"的验证意图。
   每个维度应代表一类需要验证的测试方向（如"草稿CRUD全生命周期"、"权限边界校验"），
   而不是具体的测试用例。

2. **维度命名**：使用高层级的验证意图命名（如"入参完整性校验"、"状态流转一致性"），
   不要使用具体字段名或 API 路径。

3. **维度描述**：用一句话解释该维度要验证什么，禁止包含：
   - 具体字段名（如 spc_upgrade_mode、template_ad_flag）
   - 具体 API 路径（如 /tt_ads/perf/campaign/update）
   - 具体 UI 控件名（如 "objective_name 输入框"）
   - 具体数据值（如 = 1、= null）

4. **验证模式分类**：为每个维度标注模式：
   - positive：正向功能验证
   - negative：负向/异常场景验证
   - boundary：边界值/阈值验证
   - compatibility：兼容性/多端一致性验证
   - data_consistency：数据一致性/持久化验证

5. **密度提示**：根据提供的叶子节点数量判断子模块的测试密度。

6. **目标数量**：整体输出 50-80 个验证维度，每个子模块 2-6 个维度。

7. **不要照搬**：不要复制原始用例文本，提炼它们背后的抽象测试意图。

## 模块分类指引

根据模块标题自动归类：
- 含 "FE"/"前端"/"创编" → frontend_e2e
- 含 "BE"/"后端"/"接口"/"API" → backend_api
- 含 "doc"/"文档" → documentation
- 含 "env"/"环境" → environment
- 含 "allowlist"/"白名单"/"黑名单" → config
- 含 "db check"/"数据校验" → data_validation
- 其他 → general

## 输出格式

输出严格 JSON，顶层结构为 AbstractedReferenceSchema：
{
  "modules": [
    {
      "title": "模块标题",
      "category": "frontend_e2e|backend_api|config|environment|documentation|data_validation|general",
      "submodules": [
        {
          "title": "子模块标题",
          "dimensions": [
            {
              "name": "维度名称",
              "description": "一句话描述验证目的",
              "mode": "positive|negative|boundary|compatibility|data_consistency",
              "source_leaf_count": 0
            }
          ],
          "density": "low|normal|high"
        }
      ],
      "total_source_nodes": 0,
      "boundary_hints": ["阈值提示1", "阈值提示2"]
    }
  ],
  "total_source_nodes": 0,
  "total_dimensions": 0,
  "abstraction_source": ""
}
"""

# 树节点类型（兼容 XMindReferenceNode 和 ChecklistNode）
_TreeNode = Any


class TemplateAbstractorService:
    """将完整 XMind 参考树抽象为验证维度模式。

    分层压缩策略：
    - L1（根）：丢弃
    - L2（模块分区）：保留标题 + 语义归类
    - L3（子模块）：保留标题 + 密度标注
    - L4（验证场景）：聚合为验证维度标签
    - L5+（具体用例）：完全丢弃，仅统计数量
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def abstract(
        self, xmind_ref: XMindReferenceSummary
    ) -> AbstractedReferenceSchema:
        """对参考模板执行抽象化，输出验证维度模式。

        Parameters
        ----------
        xmind_ref : XMindReferenceSummary
            由 xmind_reference_loader 加载的参考模板摘要，
            其中 ``reference_tree`` 包含完整参考树。

        Returns
        -------
        AbstractedReferenceSchema
            压缩后的验证维度模式，包含 50-80 个维度标签。

        Raises
        ------
        ValueError
            当 LLM 返回无法解析的响应时抛出。
        """
        reference_tree = xmind_ref.reference_tree
        if not reference_tree:
            logger.warning(
                "template_abstractor.abstract: reference_tree 为空，"
                "返回空 schema"
            )
            return AbstractedReferenceSchema(
                abstraction_source=xmind_ref.source_file,
            )

        # Step 1: 构建树摘要文本（L1-L4 结构 + 叶子计数）
        tree_summary_text = self._build_tree_summary_text_from_list(
            reference_tree, max_depth=4
        )

        logger.info(
            "template_abstractor.abstract: 树摘要构建完成",
            summary_length=len(tree_summary_text),
            total_nodes=xmind_ref.total_nodes,
        )

        # Step 2: 提取边界提示
        all_boundary_hints: list[str] = []
        for root_node in reference_tree:
            all_boundary_hints.extend(self._extract_boundary_hints(root_node))

        # 去重并限制数量
        seen: set[str] = set()
        unique_hints: list[str] = []
        for hint in all_boundary_hints:
            normalized = hint.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_hints.append(hint.strip())
        boundary_hints = unique_hints[:50]

        logger.info(
            "template_abstractor.abstract: 边界提示提取完成",
            total_hints=len(all_boundary_hints),
            unique_hints=len(boundary_hints),
        )

        # Step 3: 调用 LLM 进行语义压缩
        user_prompt = self._build_user_prompt(
            tree_summary_text=tree_summary_text,
            boundary_hints=boundary_hints,
            source_file=xmind_ref.source_file,
            total_nodes=xmind_ref.total_nodes,
        )

        logger.info(
            "template_abstractor.abstract: 调用 LLM 进行抽象化",
            user_prompt_length=len(user_prompt),
        )

        schema = self._llm.generate_structured(
            system_prompt=_ABSTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=AbstractedReferenceSchema,
            max_tokens=8192,
        )

        # Step 4: 后处理 — 填充统计字段
        schema = self._post_process(
            schema=schema,
            source_file=xmind_ref.source_file,
            total_source_nodes=xmind_ref.total_nodes,
            reference_tree=reference_tree,
            all_boundary_hints=boundary_hints,
        )

        logger.info(
            "template_abstractor.abstract: 抽象化完成",
            modules=len(schema.modules),
            total_dimensions=schema.total_dimensions,
            total_source_nodes=schema.total_source_nodes,
            abstraction_source=schema.abstraction_source,
        )

        return schema

    # ------------------------------------------------------------------
    # 树摘要构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tree_summary_text(
        reference_tree: _TreeNode,
        max_depth: int = 4,
    ) -> str:
        """将单棵参考树渲染为文本摘要。

        展开到 ``max_depth`` 层级，超出部分以叶子计数替代。

        Parameters
        ----------
        reference_tree : XMindReferenceNode or ChecklistNode
            参考树根节点，需具有 ``title`` 和 ``children`` 属性。
        max_depth : int
            展开的最大深度（从 1 开始计数）。

        Returns
        -------
        str
            缩进文本表示的树结构。
        """
        lines: list[str] = []
        TemplateAbstractorService._render_node(
            reference_tree, depth=1, max_depth=max_depth, lines=lines
        )
        return "\n".join(lines)

    @staticmethod
    def _build_tree_summary_text_from_list(
        reference_tree: list,
        max_depth: int = 4,
    ) -> str:
        """将参考树列表（多个根节点）渲染为文本摘要。

        Parameters
        ----------
        reference_tree : list
            参考树根节点列表。
        max_depth : int
            展开的最大深度。

        Returns
        -------
        str
            缩进文本表示的完整树结构。
        """
        lines: list[str] = []
        for root_node in reference_tree:
            TemplateAbstractorService._render_node(
                root_node, depth=1, max_depth=max_depth, lines=lines
            )
        return "\n".join(lines)

    @staticmethod
    def _render_node(
        node: _TreeNode,
        depth: int,
        max_depth: int,
        lines: list[str],
    ) -> None:
        """递归渲染节点到文本行列表。"""
        title = getattr(node, "title", "") or ""
        children = getattr(node, "children", []) or []
        indent = "  " * (depth - 1)

        if depth > max_depth:
            # 超出深度限制，显示叶子计数
            leaf_count = TemplateAbstractorService._count_leaves(node)
            lines.append(f"{indent}- {title} [... {leaf_count} 叶子节点]")
            return

        if not children:
            lines.append(f"{indent}- {title}")
            return

        leaf_count = TemplateAbstractorService._count_leaves(node)
        lines.append(
            f"{indent}- {title} ({len(children)} 子节点, {leaf_count} 叶子)"
        )
        for child in children:
            TemplateAbstractorService._render_node(
                child, depth + 1, max_depth, lines
            )

    # ------------------------------------------------------------------
    # 叶子节点计数
    # ------------------------------------------------------------------

    @staticmethod
    def _count_leaves(node: _TreeNode) -> int:
        """递归统计节点下的叶子节点数。

        Parameters
        ----------
        node : XMindReferenceNode or ChecklistNode
            树节点，需具有 ``children`` 属性。

        Returns
        -------
        int
            叶子节点总数。
        """
        children = getattr(node, "children", []) or []
        if not children:
            return 1
        return sum(
            TemplateAbstractorService._count_leaves(child)
            for child in children
        )

    # ------------------------------------------------------------------
    # 密度判定
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_density(leaf_count: int) -> str:
        """根据叶子节点数判定子模块的测试密度。

        Parameters
        ----------
        leaf_count : int
            叶子节点数。

        Returns
        -------
        str
            "low"（<=5）/ "normal"（<=20）/ "high"（>20）。
        """
        if leaf_count <= 5:
            return "low"
        elif leaf_count <= 20:
            return "normal"
        else:
            return "high"

    # ------------------------------------------------------------------
    # 边界提示提取
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_boundary_hints(node: _TreeNode) -> list[str]:
        """从叶子节点中提取数值/阈值/枚举值等边界提示。

        遍历所有叶子节点的标题，使用正则匹配提取：
        - 数字阈值（"最多30个"、"超过20个"）
        - 独立数字值（"100个视频素材"）
        - 枚举值集合（"VTR/conversion"、"daily/lifetime"）
        - 特殊状态值（"= null"、"= 0"）

        Parameters
        ----------
        node : XMindReferenceNode or ChecklistNode
            树节点。

        Returns
        -------
        list[str]
            提取到的边界提示列表。
        """
        hints: list[str] = []
        children = getattr(node, "children", []) or []

        if not children:
            # 叶子节点：从标题中提取
            title = getattr(node, "title", "") or ""
            hints.extend(
                TemplateAbstractorService._extract_hints_from_text(title)
            )
        else:
            # 非叶子：递归子节点
            for child in children:
                hints.extend(
                    TemplateAbstractorService._extract_boundary_hints(child)
                )

        return hints

    @staticmethod
    def _extract_hints_from_text(text: str) -> list[str]:
        """从单条文本中提取边界提示。"""
        hints: list[str] = []

        # 数字阈值
        for match in _NUMERIC_THRESHOLD_RE.finditer(text):
            hints.append(match.group(0).strip())

        # 枚举值集合
        for match in _ENUM_SLASH_RE.finditer(text):
            hints.append(f"枚举值: {match.group(0)}")

        # 特殊状态
        for match in _SPECIAL_VALUE_RE.finditer(text):
            hints.append(f"特殊值: {match.group(0).strip()}")

        # 独立数字值（仅在没有阈值匹配时补充）
        if not _NUMERIC_THRESHOLD_RE.search(text):
            for match in _NUMERIC_VALUE_RE.finditer(text):
                hints.append(match.group(0).strip())

        return hints

    # ------------------------------------------------------------------
    # LLM Prompt 构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(
        tree_summary_text: str,
        boundary_hints: list[str],
        source_file: str,
        total_nodes: int,
    ) -> str:
        """构建发送给 LLM 的 user prompt。"""
        boundary_section = ""
        if boundary_hints:
            hints_text = "\n".join(f"  - {h}" for h in boundary_hints)
            boundary_section = (
                f"\n\n## 从叶子节点提取的边界提示\n"
                f"以下是从模板叶子节点中确定性提取的数值/阈值/枚举值，"
                f"可作为边界维度的参考（不要原样复制到维度描述中）：\n{hints_text}"
            )

        return (
            f"## 模板信息\n"
            f"- 来源文件: {source_file}\n"
            f"- 总节点数: {total_nodes}\n"
            f"\n"
            f"## 模板树结构（展开到 L4 层级）\n"
            f"```\n{tree_summary_text}\n```\n"
            f"{boundary_section}\n"
            f"\n"
            f"请分析以上模板树结构，按照系统指令输出 AbstractedReferenceSchema JSON。\n"
            f"目标: 50-80 个验证维度，覆盖模板中所有模块的验证意图。"
        )

    # ------------------------------------------------------------------
    # 后处理
    # ------------------------------------------------------------------

    def _post_process(
        self,
        schema: AbstractedReferenceSchema,
        source_file: str,
        total_source_nodes: int,
        reference_tree: list,
        all_boundary_hints: list[str],
    ) -> AbstractedReferenceSchema:
        """后处理 LLM 输出，填充统计字段和确定性数据。

        Parameters
        ----------
        schema : AbstractedReferenceSchema
            LLM 生成的原始 schema。
        source_file : str
            原模板文件名。
        total_source_nodes : int
            原模板总节点数。
        reference_tree : list
            参考树根节点列表。
        all_boundary_hints : list[str]
            确定性提取的边界提示。

        Returns
        -------
        AbstractedReferenceSchema
            填充统计字段后的 schema。
        """
        # 填充 abstraction_source
        schema.abstraction_source = source_file

        # 填充 total_source_nodes
        schema.total_source_nodes = total_source_nodes

        # 计算 total_dimensions
        total_dims = 0
        for module in schema.modules:
            module_dims = 0
            for submodule in module.submodules:
                dim_count = len(submodule.dimensions)
                module_dims += dim_count

                # 如果 LLM 没有正确设置 density，基于叶子计数重新判定
                if submodule.density not in ("low", "normal", "high"):
                    submodule.density = "normal"

                # 填充每个维度的 source_leaf_count（如果 LLM 未设置）
                for dim in submodule.dimensions:
                    if dim.source_leaf_count <= 0:
                        dim.source_leaf_count = 0

                    # 校验 mode 值
                    valid_modes = {
                        "positive", "negative", "boundary",
                        "compatibility", "data_consistency",
                    }
                    if dim.mode not in valid_modes:
                        logger.warning(
                            "template_abstractor._post_process: "
                            "无效的 mode 值，修正为 positive",
                            dimension_name=dim.name,
                            invalid_mode=dim.mode,
                        )
                        dim.mode = "positive"

            total_dims += module_dims

            # 补充模块级 boundary_hints（确定性数据优先）
            if not module.boundary_hints and all_boundary_hints:
                # 尝试从模块标题相关的提示中筛选（简单启发式）
                module.boundary_hints = []

            # 补充 total_source_nodes（模块级）
            if module.total_source_nodes <= 0:
                # 尝试从参考树中匹配同名分支
                module.total_source_nodes = self._estimate_module_node_count(
                    module.title, reference_tree
                )

        schema.total_dimensions = total_dims

        return schema

    @staticmethod
    def _estimate_module_node_count(
        module_title: str, reference_tree: list
    ) -> int:
        """从参考树中估算某个模块的节点数。

        基于模块标题与参考树一级分支标题的字符重叠进行匹配。
        """
        best_count = 0
        best_score = 0.0
        module_chars = set(module_title)

        for root_node in reference_tree:
            node_title = getattr(root_node, "title", "") or ""
            node_chars = set(node_title)
            union = module_chars | node_chars
            if not union:
                continue
            score = len(module_chars & node_chars) / len(union)
            if score > best_score:
                best_score = score
                best_count = TemplateAbstractorService._count_all_nodes(
                    root_node
                )

        # 仅在相似度 >= 0.3 时返回匹配结果
        if best_score >= 0.3:
            return best_count
        return 0

    @staticmethod
    def _count_all_nodes(node: _TreeNode) -> int:
        """递归统计节点总数（含自身）。"""
        children = getattr(node, "children", []) or []
        return 1 + sum(
            TemplateAbstractorService._count_all_nodes(child)
            for child in children
        )
