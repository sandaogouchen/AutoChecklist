"""评测基准对比领域模型。

定义 XMind 评测基准对比流程中使用的数据结构：
- ``LeafCase``：从 XMind 提取的叶子用例
- ``CasePair``：匹配后的用例对
- ``ScoredPair``：LLM 评分后的用例对
- ``BenchmarkMetrics``：聚合指标
- ``ImprovementSuggestion``：LLM 改进建议
- ``BenchmarkRequest``：API 请求
- ``BenchmarkReport``：完整评测报告
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LeafCase(BaseModel):
    """从 XMind 提取的叶子节点用例。

    Attributes:
        title: 叶子节点标题（即用例描述）。
        path: 从根到叶子的祖先节点标题列表。
        full_path_str: 以 " > " 连接的完整路径字符串，用于匹配。
    """

    title: str
    path: list[str] = Field(default_factory=list)
    full_path_str: str = ""


class CasePair(BaseModel):
    """匹配后的用例对（LLM 评分前）。

    Attributes:
        ai_case: AI 生成的用例。
        gt_case: 人工基准用例。
        text_similarity: 文本预匹配相似度（0-1）。
    """

    ai_case: LeafCase
    gt_case: LeafCase
    text_similarity: float = 0.0


class ScoredPair(BaseModel):
    """LLM 评分后的用例对。

    Attributes:
        ai_case: AI 生成的用例。
        gt_case: 人工基准用例。
        text_similarity: 文本预匹配相似度。
        llm_similarity: LLM 判定的语义相似度（0-1）。
        diff_summary: LLM 生成的差异摘要。
        is_match: 是否视为匹配成功（llm_similarity >= 阈值）。
    """

    ai_case: LeafCase
    gt_case: LeafCase
    text_similarity: float = 0.0
    llm_similarity: float = 0.0
    diff_summary: str = ""
    is_match: bool = False


class BenchmarkMetrics(BaseModel):
    """评测聚合指标。

    Attributes:
        total_ai_cases: AI 生成的用例总数。
        total_gt_cases: 人工基准用例总数。
        matched_count: 匹配成功的用例对数量。
        unmatched_ai_cases: AI 中多余的用例（过度生成）。
        uncovered_gt_cases: 基准中未被覆盖的用例（遗漏）。
        precision: 精确率 = matched / total_ai。
        recall: 召回率 = matched / total_gt。
        f1: F1 分数 = 2*P*R / (P+R)。
        avg_similarity: 所有配对的平均 LLM 相似度。
        similarity_distribution: 相似度分桶统计。
    """

    total_ai_cases: int = 0
    total_gt_cases: int = 0
    matched_count: int = 0
    unmatched_ai_cases: list[LeafCase] = Field(default_factory=list)
    uncovered_gt_cases: list[LeafCase] = Field(default_factory=list)
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    avg_similarity: float = 0.0
    similarity_distribution: dict[str, int] = Field(default_factory=dict)


class ImprovementSuggestion(BaseModel):
    """LLM 生成的改进建议。

    Attributes:
        overall_assessment: 总体评价。
        strength_areas: AI 表现好的方面。
        weakness_areas: AI 需要改进的方面。
        specific_improvements: 具体改进建议列表。
        priority_actions: 优先执行的改进动作。
    """

    overall_assessment: str = ""
    strength_areas: list[str] = Field(default_factory=list)
    weakness_areas: list[str] = Field(default_factory=list)
    specific_improvements: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)


class PairEvaluation(BaseModel):
    """单对用例的 LLM 评分结果。"""

    pair_index: int
    similarity: float = 0.0
    diff_summary: str = ""


class BatchEvaluationResult(BaseModel):
    """批量用例对的 LLM 评分结果集合。"""

    evaluations: list[PairEvaluation] = Field(default_factory=list)


class BenchmarkRequest(BaseModel):
    """评测基准对比 API 请求体。

    Attributes:
        ai_xmind_path: AI 生成的 .xmind 文件本地路径。
        gt_xmind_path: 人工基准 .xmind 文件本地路径。
        similarity_threshold: 判定匹配成功的相似度阈值。
        batch_size: 每批 LLM 评分的用例对数量。
    """

    ai_xmind_path: str
    gt_xmind_path: str
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    batch_size: int = Field(default=5, ge=1, le=50)


class BenchmarkReport(BaseModel):
    """完整评测基准对比报告。

    Attributes:
        benchmark_id: 评测运行标识。
        ai_xmind_path: AI XMind 文件路径。
        gt_xmind_path: 基准 XMind 文件路径。
        metrics: 聚合指标。
        scored_pairs: 所有评分后的用例对详情。
        improvement: LLM 改进建议。
        timestamp: 评测时间戳。
    """

    benchmark_id: str = ""
    ai_xmind_path: str = ""
    gt_xmind_path: str = ""
    metrics: BenchmarkMetrics = Field(default_factory=BenchmarkMetrics)
    scored_pairs: list[ScoredPair] = Field(default_factory=list)
    improvement: ImprovementSuggestion = Field(
        default_factory=ImprovementSuggestion,
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )
