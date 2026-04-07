#!/usr/bin/env python3
"""AutoChecklist 回归评估 CLI。

用法:
    # Phase 1 only（结构对比，不调 LLM）
    python scripts/regression_eval.py --config regression_config.yaml --phase 1

    # Phase 1 + Phase 2（结构对比 + LLM 双盲评估）
    python scripts/regression_eval.py --config regression_config.yaml

    # 直接指定目录（不用配置文件）
    python scripts/regression_eval.py \\
        --baseline output/runs/RUN-20260406-001 \\
        --candidate output/runs/RUN-20260407-001 \\
        --prd testprd.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.regression_models import RegressionConfig, MetricDelta
from app.services.regression_evaluator import RegressionEvaluator


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

STATUS_ICONS = {
    "OK": "✅",
    "WARNING": "⚠️ ",
    "REGRESSED": "❌",
    "CRITICAL": "🔴",
    "REGRESSION": "❌",
}


def render_report(report) -> str:
    """将 RegressionReport 渲染为终端友好的文本。"""
    lines: list[str] = []

    lines.append("══════════════════════════════════════════════════════")
    lines.append("  AutoChecklist Regression Evaluation")
    lines.append("══════════════════════════════════════════════════════")
    lines.append("")

    diff = report.structural_diff
    if diff:
        b = diff.baseline_fingerprint
        c = diff.candidate_fingerprint
        lines.append(f"Baseline:  {b.label or b.run_dir}")
        lines.append(f"Candidate: {c.label or c.run_dir}")
        lines.append("")

        # Phase 1
        lines.append("── Phase 1: Structural Comparison ──────────────────")
        lines.append("")
        lines.append(f"{'':26s} {'Baseline':>10s} {'Candidate':>10s} {'Delta':>10s}  Status")
        lines.append(f"{'─' * 76}")

        for name, m in diff.metric_deltas.items():
            icon = STATUS_ICONS.get(m.status, "")
            bv = _fmt_val(m.baseline_value)
            cv = _fmt_val(m.candidate_value)
            lines.append(f"{name:26s} {bv:>10s} {cv:>10s} {m.delta:>10s}  {icon} {m.status}")

        lines.append("")

        if diff.baseline_only:
            lines.append(f"Cases only in baseline ({len(diff.baseline_only)}):")
            for tc in diff.baseline_only[:10]:
                lines.append(f"  - [{tc.get('id', '?')}] {tc.get('title', '?')} ({tc.get('priority', '?')})")
            if len(diff.baseline_only) > 10:
                lines.append(f"  ... and {len(diff.baseline_only) - 10} more")
            lines.append("")

        if diff.candidate_only:
            lines.append(f"Cases only in candidate ({len(diff.candidate_only)}):")
            for tc in diff.candidate_only[:10]:
                lines.append(f"  - [{tc.get('id', '?')}] {tc.get('title', '?')} ({tc.get('priority', '?')})")
            if len(diff.candidate_only) > 10:
                lines.append(f"  ... and {len(diff.candidate_only) - 10} more")
            lines.append("")

        lines.append(f"Phase 1 Verdict: {STATUS_ICONS.get(diff.verdict, '')} {diff.verdict}")
        lines.append("")

    # Phase 2
    blind = report.blind_verdict
    if blind:
        lines.append("── Phase 2: LLM Blind Evaluation ───────────────────")
        lines.append("")
        lines.append(f"Surface diff: {blind.surface_analysis}")
        lines.append("")
        lines.append("Quality analysis:")
        for line in blind.quality_analysis.split("\n"):
            lines.append(f"  {line}")
        lines.append("")
        lines.append(f"Winner: {blind.overall_winner} (confidence: {blind.confidence:.0%})")
        if blind.key_reasons:
            lines.append("Key reasons:")
            for i, reason in enumerate(blind.key_reasons[:5], 1):
                lines.append(f"  {i}. {reason}")
        lines.append("")

        phase2_icon = STATUS_ICONS.get(
            "REGRESSION" if blind.overall_winner == "baseline" else "OK", ""
        )
        phase2_verdict = "REGRESSION" if blind.overall_winner == "baseline" else "OK"
        lines.append(f"Phase 2 Verdict: {phase2_icon} {phase2_verdict}")
        lines.append("")

    # Overall
    lines.append("══════════════════════════════════════════════════════")
    icon = STATUS_ICONS.get(report.overall_verdict, "")
    lines.append(f"  OVERALL: {icon} {report.overall_verdict}")
    lines.append("══════════════════════════════════════════════════════")

    return "\n".join(lines)


def _fmt_val(v) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AutoChecklist 回归评估工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config", "-c",
        help="YAML 配置文件路径",
    )
    parser.add_argument(
        "--baseline", "-b",
        help="基线运行目录（覆盖配置文件）",
    )
    parser.add_argument(
        "--candidate", "-d",
        help="候选运行目录（覆盖配置文件）",
    )
    parser.add_argument(
        "--prd",
        help="PRD 文件路径（覆盖配置文件）",
    )
    parser.add_argument(
        "--baseline-label",
        help="基线标签（用于报告显示）",
    )
    parser.add_argument(
        "--candidate-label",
        help="候选标签（用于报告显示）",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2],
        default=2,
        help="评估阶段：1=仅结构对比，2=结构+LLM（默认 2）",
    )
    parser.add_argument(
        "--output", "-o",
        help="输出报告 JSON 文件路径（可选）",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> RegressionConfig:
    """从 YAML 和命令行参数构建配置。"""
    config_data: dict = {}

    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        else:
            print(f"WARNING: 配置文件不存在: {args.config}", file=sys.stderr)

    # 命令行参数覆盖
    if args.baseline:
        config_data["baseline_run_dir"] = args.baseline
    if args.candidate:
        config_data["candidate_run_dir"] = args.candidate
    if args.prd:
        config_data["prd_path"] = args.prd
    if args.baseline_label:
        config_data["baseline_label"] = args.baseline_label
    if args.candidate_label:
        config_data["candidate_label"] = args.candidate_label

    # 校验必填项
    if not config_data.get("baseline_run_dir"):
        print("ERROR: 必须指定 baseline_run_dir（通过 --config 或 --baseline）", file=sys.stderr)
        sys.exit(1)
    if not config_data.get("candidate_run_dir"):
        print("ERROR: 必须指定 candidate_run_dir（通过 --config 或 --candidate）", file=sys.stderr)
        sys.exit(1)

    return RegressionConfig(**config_data)


def main() -> None:
    args = parse_args()
    config = load_config(args)

    llm_client = None
    if args.phase >= 2 and config.prd_path:
        try:
            from app.clients.llm import OpenAICompatibleLLMClient, LLMClientConfig
            from app.config.settings import get_settings

            settings = get_settings()
            llm_config = LLMClientConfig(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                timeout=settings.llm_timeout_seconds,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            llm_client = OpenAICompatibleLLMClient(llm_config)
            print("LLM 客户端已初始化，将执行 Phase 2 双盲评估")
        except Exception as exc:
            print(f"WARNING: LLM 客户端初始化失败: {exc}", file=sys.stderr)
            print("将仅执行 Phase 1 结构对比", file=sys.stderr)

    if args.phase == 1:
        llm_client = None
        # Phase 1 only 时清除 prd_path 避免触发 Phase 2
        config = config.model_copy(update={"prd_path": ""})

    evaluator = RegressionEvaluator(llm_client=llm_client)
    report = evaluator.run(config)

    # 渲染终端输出
    print(render_report(report))

    # 可选：输出 JSON
    if args.output:
        import json

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"\n报告已保存: {output_path}")

    # 退出码
    if report.overall_verdict == "REGRESSION":
        sys.exit(1)
    elif report.overall_verdict == "WARNING":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
