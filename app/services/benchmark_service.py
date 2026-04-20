"""评测基准对比编排服务。

协调 XMind 解析、用例匹配、LLM 评分、指标聚合和改进建议生成，
输出完整的 BenchmarkReport 并持久化到文件系统。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.clients.llm import LLMClient, LLMClientConfig, OpenAICompatibleLLMClient
from app.config.settings import Settings
from app.domain.benchmark_models import (
    BenchmarkMetrics,
    BenchmarkReport,
    BenchmarkRequest,
    LeafCase,
    ScoredPair,
)
from app.domain.xmind_reference_models import XMindReferenceNode
from app.parsers.xmind_parser import XMindParser
from app.services.benchmark_analyzer import BenchmarkAnalyzer
from app.services.benchmark_evaluator import BenchmarkEvaluator
from app.services.benchmark_matcher import BenchmarkMatcher
from app.utils.run_id import generate_run_id

logger = logging.getLogger(__name__)


class BenchmarkService:
    """评测基准对比编排服务。

    完整流程：
    1. 解析两个 XMind 文件，提取叶子用例（含路径上下文）
    2. 贪心最优匹配
    3. LLM 逐对精确评分
    4. 指标聚合
    5. LLM 改进建议生成
    6. 结果持久化
    """

    def __init__(
        self,
        settings: Settings,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._settings = settings
        self._xmind_parser = XMindParser()
        self._matcher = BenchmarkMatcher()

        # LLM 客户端：复用或新建
        if llm_client is not None:
            self._llm = llm_client
        else:
            config = LLMClientConfig(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                timeout_seconds=settings.llm_timeout_seconds,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            self._llm = OpenAICompatibleLLMClient(config)

        self._evaluator = BenchmarkEvaluator(self._llm)
        self._analyzer = BenchmarkAnalyzer(self._llm)
        self._output_dir = Path(settings.output_dir) / "benchmark_runs"

    def run_benchmark(self, request: BenchmarkRequest) -> BenchmarkReport:
        """执行完整的评测基准对比流程。

        Args:
            request: 评测请求，包含两个 XMind 路径和配置参数。

        Returns:
            完整的 BenchmarkReport。
        """
        for p in [request.ai_xmind_path, request.gt_xmind_path]:
            if not Path(p).exists():
                raise FileNotFoundError(f"XMind file not found: {p}")

        benchmark_id = generate_run_id(
            output_dir=self._output_dir,
            timezone=self._settings.timezone,
        )
        logger.info("开始评测: %s", benchmark_id)

        # 1. 解析 XMind，提取叶子用例
        logger.info("解析 AI XMind: %s", request.ai_xmind_path)
        ai_leaves = self._extract_leaves(request.ai_xmind_path)
        logger.info("AI XMind 叶子用例数: %d", len(ai_leaves))

        logger.info("解析基准 XMind: %s", request.gt_xmind_path)
        gt_leaves = self._extract_leaves(request.gt_xmind_path)
        logger.info("基准 XMind 叶子用例数: %d", len(gt_leaves))

        # 2. 匹配
        pairs, unmatched_ai, uncovered_gt = self._matcher.match(
            ai_leaves, gt_leaves
        )
        logger.info("匹配完成: %d 对", len(pairs))

        # 3. LLM 逐对评分
        scored_pairs = self._evaluator.evaluate_pairs(
            pairs,
            batch_size=request.batch_size,
            similarity_threshold=request.similarity_threshold,
        )

        # 4. 指标聚合
        metrics = BenchmarkAnalyzer.compute_metrics(
            scored_pairs,
            unmatched_ai,
            uncovered_gt,
            threshold=request.similarity_threshold,
        )
        logger.info(
            "指标: P=%.4f R=%.4f F1=%.4f avg_sim=%.4f",
            metrics.precision,
            metrics.recall,
            metrics.f1,
            metrics.avg_similarity,
        )

        # 5. LLM 改进建议
        improvement = self._analyzer.generate_improvement_suggestions(
            metrics, scored_pairs, unmatched_ai, uncovered_gt
        )

        # 6. 组装报告
        report = BenchmarkReport(
            benchmark_id=benchmark_id,
            ai_xmind_path=request.ai_xmind_path,
            gt_xmind_path=request.gt_xmind_path,
            metrics=metrics,
            scored_pairs=scored_pairs,
            improvement=improvement,
            timestamp=datetime.now().isoformat(),
        )

        # 7. 持久化
        self._persist(benchmark_id, request, report)
        logger.info("评测完成: %s", benchmark_id)

        return report

    # ------------------------------------------------------------------
    # XMind 叶子提取
    # ------------------------------------------------------------------

    def _extract_leaves(self, xmind_path: str) -> list[LeafCase]:
        """解析 XMind 文件并提取所有叶子用例（含路径上下文）。

        Args:
            xmind_path: .xmind 文件的本地路径。

        Returns:
            LeafCase 列表。
        """
        root = self._xmind_parser.parse(xmind_path)
        leaves: list[LeafCase] = []
        self._collect_leaves_with_path(root, [], leaves)
        return leaves

    def _collect_leaves_with_path(
        self,
        node: XMindReferenceNode,
        current_path: list[str],
        acc: list[LeafCase],
    ) -> None:
        """递归收集叶子节点，附带完整祖先路径。"""
        path = current_path + [node.title]
        if not node.children:
            acc.append(
                LeafCase(
                    title=node.title,
                    path=path,
                    full_path_str=" > ".join(path),
                )
            )
        else:
            for child in node.children:
                self._collect_leaves_with_path(child, path, acc)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _persist(
        self,
        benchmark_id: str,
        request: BenchmarkRequest,
        report: BenchmarkReport,
    ) -> None:
        """将评测结果持久化到文件系统。

        目录结构：
        output/benchmark_runs/<benchmark_id>/
        ├── request.json
        ├── report.json
        ├── scored_pairs.json
        └── improvement.json
        """
        run_dir = self._output_dir / benchmark_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # request.json
        (run_dir / "request.json").write_text(
            request.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # report.json（完整报告）
        (run_dir / "report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # scored_pairs.json（仅配对详情，方便分析）
        pairs_data = [p.model_dump(mode="json") for p in report.scored_pairs]
        (run_dir / "scored_pairs.json").write_text(
            json.dumps(pairs_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # improvement.json（仅改进建议）
        (run_dir / "improvement.json").write_text(
            report.improvement.model_dump_json(indent=2),
            encoding="utf-8",
        )

        logger.info("评测结果已持久化到: %s", run_dir)
