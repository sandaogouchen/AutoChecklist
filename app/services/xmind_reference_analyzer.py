"""XMind 参考文件结构分析服务。

对解析后的 XMind 树执行确定性结构分析（无 LLM 调用、无 IO），
生成可注入 prompt 的摘要信息。

分析策略（方案 A：结构摘要 + 代表性路径抽取）：
1. 骨架提取 — 前 3 层缩进文本
2. 代表性路径采样 — 每个一级分支均匀采样最多 5 条叶子路径
3. 统计信息 — 深度分布、叶子数、常用前缀
4. 路由建议 — 基于参考结构为 checkpoint 生成归属建议
"""

from __future__ import annotations

import random
from collections import Counter

from app.domain.xmind_reference_models import XMindReferenceNode, XMindReferenceSummary

# 骨架提取的最大深度（含根节点共 4 层）
_SKELETON_MAX_DEPTH = 3

# 每个一级分支的最大采样路径数
_MAX_PATHS_PER_BRANCH = 5

# 采样固定种子，保证可复现
_SAMPLING_SEED = 42

# 路由建议的 Jaccard 相似度阈值
_ROUTING_SIMILARITY_THRESHOLD = 0.3

# 常用前缀取 top-N
_TOP_PREFIX_COUNT = 10


class XMindReferenceAnalyzer:
    """XMind 参考文件结构分析器。

    所有方法为纯 CPU 计算，无副作用，易于单元测试。
    """

    def analyze(
        self,
        root: XMindReferenceNode,
        source_file: str,
    ) -> XMindReferenceSummary:
        """对 XMind 树执行结构分析，返回可注入 prompt 的摘要。

        Args:
            root: XMind 解析后的根节点。
            source_file: 原始文件路径（记录用）。

        Returns:
            ``XMindReferenceSummary`` 包含骨架、采样路径、统计信息和格式化摘要。
        """
        total_nodes = self._count_nodes(root)
        total_leaf_nodes = self._count_leaf_nodes(root)
        max_depth = self._max_depth(root)
        depth_dist = self._depth_distribution(root)
        skeleton = self._extract_skeleton(root, max_depth=_SKELETON_MAX_DEPTH)
        sampled_paths = self._sample_representative_paths(root)
        top_prefixes = self._extract_top_prefixes(root)
        formatted_summary = self._render_formatted_summary(
            skeleton=skeleton,
            sampled_paths=sampled_paths,
            total_nodes=total_nodes,
            total_leaf_nodes=total_leaf_nodes,
            max_depth=max_depth,
            depth_distribution=depth_dist,
        )

        return XMindReferenceSummary(
            source_file=source_file,
            total_nodes=total_nodes,
            total_leaf_nodes=total_leaf_nodes,
            max_depth=max_depth,
            skeleton=skeleton,
            sampled_paths=sampled_paths,
            depth_distribution=depth_dist,
            top_prefixes=top_prefixes,
            formatted_summary=formatted_summary,
        )

    def generate_routing_hints(
        self,
        summary: XMindReferenceSummary,
        checkpoint_titles: list[str],
    ) -> str:
        """基于参考结构为 checkpoint 列表生成归属建议文本。

        从 skeleton 中提取一级/二级分支名称，对每个 checkpoint 标题
        做字符级 Jaccard 相似度匹配，输出路由建议。

        Args:
            summary: 已生成的参考摘要。
            checkpoint_titles: 待归属的 checkpoint 标题列表。

        Returns:
            可直接注入 prompt 的路由建议文本。
        """
        branches = self._extract_branch_names_from_skeleton(summary.skeleton)
        if not branches or not checkpoint_titles:
            return ""

        lines: list[str] = []
        for title in checkpoint_titles:
            best_branch, best_score = self._find_best_match(title, branches)
            if best_score >= _ROUTING_SIMILARITY_THRESHOLD:
                lines.append(f'- "{title}" → 建议归属: {best_branch}')
            else:
                lines.append(f'- "{title}" → 无明确归属，建议新建分支')

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _count_nodes(node: XMindReferenceNode) -> int:
        """递归统计节点总数。"""
        return 1 + sum(
            XMindReferenceAnalyzer._count_nodes(c) for c in node.children
        )

    @staticmethod
    def _count_leaf_nodes(node: XMindReferenceNode) -> int:
        """递归统计叶子节点数。"""
        if not node.children:
            return 1
        return sum(
            XMindReferenceAnalyzer._count_leaf_nodes(c) for c in node.children
        )

    @staticmethod
    def _max_depth(node: XMindReferenceNode, current: int = 0) -> int:
        """递归计算最大深度。"""
        if not node.children:
            return current
        return max(
            XMindReferenceAnalyzer._max_depth(c, current + 1)
            for c in node.children
        )

    @staticmethod
    def _depth_distribution(
        node: XMindReferenceNode,
        current: int = 0,
    ) -> dict[int, int]:
        """统计各深度层级的节点数量。"""
        dist: dict[int, int] = {current: 1}
        for child in node.children:
            child_dist = XMindReferenceAnalyzer._depth_distribution(
                child, current + 1
            )
            for depth, count in child_dist.items():
                dist[depth] = dist.get(depth, 0) + count
        return dist

    @staticmethod
    def _extract_skeleton(
        node: XMindReferenceNode,
        max_depth: int,
        current_depth: int = 0,
        prefix: str = "",
    ) -> str:
        """提取前 N 层骨架，超出部分以省略标记表示。"""
        lines: list[str] = []
        line = f"{prefix}{node.title}"

        if current_depth > max_depth:
            return ""

        if current_depth == max_depth and node.children:
            child_count = XMindReferenceAnalyzer._count_nodes(node) - 1
            line += f"  ...（{child_count} 个子项）"
            lines.append(line)
            return "\n".join(lines)

        lines.append(line)
        for i, child in enumerate(node.children):
            is_last = i == len(node.children) - 1
            child_prefix = prefix + ("    " if is_last else "│   ")
            connector = "└── " if is_last else "├── "
            child_skeleton = XMindReferenceAnalyzer._extract_skeleton(
                child,
                max_depth,
                current_depth + 1,
                prefix=prefix + ("    " if is_last else "│   "),
            )
            if child_skeleton:
                # 替换第一行的前缀为带连接符的版本
                child_lines = child_skeleton.split("\n")
                first_line = child_lines[0].replace(
                    child_prefix, prefix + connector, 1
                )
                child_lines[0] = first_line
                lines.extend(child_lines)

        return "\n".join(lines)

    @staticmethod
    def _sample_representative_paths(
        root: XMindReferenceNode,
    ) -> list[str]:
        """每个一级分支均匀采样最多 N 条叶子完整路径。"""
        all_paths: list[str] = []
        rng = random.Random(_SAMPLING_SEED)

        for branch in root.children:
            leaf_paths = XMindReferenceAnalyzer._collect_leaf_paths(
                branch, prefix=root.title
            )
            if len(leaf_paths) <= _MAX_PATHS_PER_BRANCH:
                all_paths.extend(leaf_paths)
            else:
                # 均匀间隔采样
                step = len(leaf_paths) / _MAX_PATHS_PER_BRANCH
                indices = [int(i * step) for i in range(_MAX_PATHS_PER_BRANCH)]
                sampled = [leaf_paths[i] for i in indices]
                # 用固定种子做轻微随机扰动，保持可复现
                rng.shuffle(sampled)
                all_paths.extend(sorted(sampled))

        return all_paths

    @staticmethod
    def _collect_leaf_paths(
        node: XMindReferenceNode,
        prefix: str = "",
    ) -> list[str]:
        """收集节点下所有叶子节点的完整路径。"""
        current_path = f"{prefix} > {node.title}" if prefix else node.title
        if not node.children:
            return [current_path]
        paths: list[str] = []
        for child in node.children:
            paths.extend(
                XMindReferenceAnalyzer._collect_leaf_paths(child, current_path)
            )
        return paths

    @staticmethod
    def _extract_top_prefixes(
        root: XMindReferenceNode,
    ) -> list[str]:
        """提取出现频率最高的路径前缀（二级路径）。"""
        prefixes: list[str] = []
        for branch in root.children:
            for child in branch.children:
                prefixes.append(f"{root.title} > {branch.title} > {child.title}")
        counter = Counter(prefixes)
        return [p for p, _ in counter.most_common(_TOP_PREFIX_COUNT)]

    @staticmethod
    def _render_formatted_summary(
        skeleton: str,
        sampled_paths: list[str],
        total_nodes: int,
        total_leaf_nodes: int,
        max_depth: int,
        depth_distribution: dict[int, int],
    ) -> str:
        """渲染 prompt 可注入的格式化摘要文本。"""
        paths_text = "\n".join(f"  - {p}" for p in sampled_paths)
        depth_text = ", ".join(
            f"深度{d}: {c}个" for d, c in sorted(depth_distribution.items())
        )

        return (
            "[参考 Checklist 结构]\n"
            "以下是一份已有的高质量 Checklist 结构摘要，"
            "请参考其覆盖维度、命名风格和组织方式：\n\n"
            "## 结构骨架\n"
            f"{skeleton}\n\n"
            "## 代表性路径示例\n"
            f"{paths_text}\n\n"
            "## 统计概况\n"
            f"- 总节点数: {total_nodes}\n"
            f"- 叶子用例数: {total_leaf_nodes}\n"
            f"- 最大深度: {max_depth}\n"
            f"- 深度分布: {depth_text}\n"
        )

    @staticmethod
    def _extract_branch_names_from_skeleton(skeleton: str) -> list[str]:
        """从骨架文本中提取一级和二级分支名称。

        解析缩进和连接符来确定层级，提取前两层分支作为路由目标。
        返回格式如 "一级分支" 或 "一级分支 > 二级分支"。
        """
        if not skeleton:
            return []

        branches: list[str] = []
        lines = skeleton.split("\n")
        current_l1 = ""

        for line in lines[1:]:  # 跳过根节点行
            stripped = line.lstrip("│ ")
            # 检测连接符
            for connector in ("├── ", "└── "):
                if connector in stripped:
                    name = stripped.split(connector, 1)[1]
                    # 去掉省略标记
                    if "  ...(" in name or "  ...（" in name:
                        name = name.split("  ...")[0]
                    # 判断层级：第一层缩进较少
                    indent = len(line) - len(line.lstrip())
                    if indent <= 4:  # 一级分支
                        current_l1 = name.strip()
                        branches.append(current_l1)
                    elif indent <= 12 and current_l1:  # 二级分支
                        branches.append(
                            f"{current_l1} > {name.strip()}"
                        )
                    break

        return branches

    @staticmethod
    def _find_best_match(
        title: str,
        branches: list[str],
    ) -> tuple[str, float]:
        """字符级 Jaccard 相似度匹配。

        Returns:
            (最佳匹配分支, 相似度分数) 元组。
        """
        title_chars = set(title)
        best_branch = ""
        best_score = 0.0

        for branch in branches:
            branch_chars = set(branch)
            intersection = title_chars & branch_chars
            union = title_chars | branch_chars
            if not union:
                continue
            score = len(intersection) / len(union)
            if score > best_score:
                best_score = score
                best_branch = branch

        return best_branch, best_score
