"""运行状态持久化仓储。

基于文件系统的运行状态存储实现，负责持久化和读取：
- run_state.json：完整运行状态
- evaluation_report.json：结构化评估报告
- iteration_log.json：迭代历史记录
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domain.run_state import EvaluationReport, RunState
from app.utils.filesystem import read_json, write_json


class RunStateRepository:
    """基于文件系统的运行状态仓储。

    与 FileRunRepository 配合使用，将迭代评估回路的状态信息
    持久化到相同的 run 目录下。
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def save_run_state(self, run_state: RunState) -> Path:
        """持久化运行状态到 run_state.json。"""
        return self._save(
            run_state.run_id,
            run_state.model_dump(mode="json"),
            "run_state.json",
        )

    def load_run_state(self, run_id: str) -> RunState:
        """从 run_state.json 加载运行状态。"""
        data = self._load(run_id, "run_state.json")
        return RunState.model_validate(data)

    def save_evaluation_report(
        self,
        run_id: str,
        report: EvaluationReport,
        iteration_index: int = 0,
    ) -> Path:
        """持久化评估报告到 evaluation_report.json。

        如果有多轮迭代，同时保存历史版本 evaluation_report_iter_{N}.json。
        """
        data = report.model_dump(mode="json")

        # 保存当前版本（总是覆写）
        main_path = self._save(run_id, data, "evaluation_report.json")

        # 保存历史版本
        if iteration_index > 0:
            self._save(
                run_id,
                data,
                f"evaluation_report_iter_{iteration_index}.json",
            )

        return main_path

    def load_evaluation_report(self, run_id: str) -> EvaluationReport:
        """从 evaluation_report.json 加载评估报告。"""
        data = self._load(run_id, "evaluation_report.json")
        return EvaluationReport.model_validate(data)

    def save_iteration_log(self, run_state: RunState) -> Path:
        """从 RunState 的迭代历史中提取并保存 iteration_log.json。"""
        log_data = {
            "run_id": run_state.run_id,
            "total_iterations": len(run_state.iteration_history),
            "final_status": run_state.status.value,
            "iterations": [
                record.model_dump(mode="json")
                for record in run_state.iteration_history
            ],
            "retry_decisions": [
                decision.model_dump(mode="json")
                for decision in run_state.retry_decisions
            ],
        }
        return self._save(run_state.run_id, log_data, "iteration_log.json")

    def load_iteration_log(self, run_id: str) -> dict[str, Any]:
        """加载 iteration_log.json。"""
        return self._load(run_id, "iteration_log.json")

    def run_state_exists(self, run_id: str) -> bool:
        """检查指定 run 的 run_state.json 是否存在。"""
        return (self._run_dir(run_id) / "run_state.json").exists()

    def _save(self, run_id: str, payload: dict[str, Any], filename: str) -> Path:
        """保存 JSON 数据到指定 run 目录下的文件。"""
        target_path = self._run_dir(run_id) / filename
        write_json(target_path, payload)
        return target_path

    def _load(self, run_id: str, filename: str) -> dict[str, Any]:
        """从指定 run 目录下加载 JSON 文件。"""
        return read_json(self._run_dir(run_id) / filename)

    def _run_dir(self, run_id: str) -> Path:
        """获取 run 目录路径（不自动创建）。"""
        run_dir = self.root_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
