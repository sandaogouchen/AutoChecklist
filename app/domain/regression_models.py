"""回归评估领域模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegressionConfig(BaseModel):
    """回归评估配置。"""

    baseline_run_dir: str
    candidate_run_dir: str
    prd_path: str = ""
    baseline_label: str = ""
    candidate_label: str = ""


class RunFingerprint(BaseModel):
    """单次运行的结构化指纹。"""

    run_dir: str
    label: str = ""
    total_test_cases: int = 0
    total_checkpoints: int = 0
    avg_steps_per_case: float = 0.0
    cases_with_evidence: int = 0
    cases_with_preconditions: int = 0
    unique_title_ratio: float = 1.0
    category_distribution: dict[str, int] = Field(default_factory=dict)
    priority_distribution: dict[str, int] = Field(default_factory=dict)
    mr_analysis_present: bool = False
    six_dim_scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0
    test_cases_raw: list[dict] = Field(default_factory=list)


class CaseMatch(BaseModel):
    """一对配对的用例。"""

    baseline_case: dict
    candidate_case: dict
    match_score: float = 0.0
    match_key: str = ""


class MetricDelta(BaseModel):
    """单个指标的对比结果。"""

    baseline_value: float | int | bool | str = 0
    candidate_value: float | int | bool | str = 0
    delta: str = ""
    status: str = "OK"  # OK / WARNING / REGRESSED / CRITICAL


class StructuralDiff(BaseModel):
    """Phase 1 结构对比结果。"""

    baseline_fingerprint: RunFingerprint
    candidate_fingerprint: RunFingerprint
    matched_pairs: list[CaseMatch] = Field(default_factory=list)
    baseline_only: list[dict] = Field(default_factory=list)
    candidate_only: list[dict] = Field(default_factory=list)
    metric_deltas: dict[str, MetricDelta] = Field(default_factory=dict)
    verdict: str = "OK"


class DiffAnalysisItem(BaseModel):
    """LLM 对单个差异项的分析。"""

    item: str
    verdict: str = ""  # "A_better" / "B_better" / "tie"
    reason: str = ""


class BlindEvalResponse(BaseModel):
    """LLM 双盲评估的结构化输出。

    作为 generate_structured 的 response_model。
    """

    surface_diff_summary: str = ""
    diff_analysis: list[DiffAnalysisItem] = Field(default_factory=list)
    overall_winner: str = "tie"  # "A" / "B" / "tie"
    confidence: float = 0.0
    one_line_conclusion: str = ""


class BlindVerdict(BaseModel):
    """去盲后的评估结论。"""

    surface_analysis: str = ""
    quality_analysis: str = ""
    overall_winner: str = "tie"  # "baseline" / "candidate" / "tie"
    confidence: float = 0.0
    key_reasons: list[str] = Field(default_factory=list)
    baseline_was_set: str = ""  # "A" or "B"
    raw_response: BlindEvalResponse | None = None


class RegressionReport(BaseModel):
    """完整回归报告。"""

    structural_diff: StructuralDiff | None = None
    blind_verdict: BlindVerdict | None = None
    overall_verdict: str = "UNKNOWN"
    summary: str = ""
