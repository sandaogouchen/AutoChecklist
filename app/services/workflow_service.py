"""Orchestrates a full workflow run."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from app.domain.run_state import RunRecord, RunStatus
from app.graphs.main_workflow import build_workflow

logger = logging.getLogger(__name__)


class WorkflowService:
    """Thin wrapper that builds the graph, invokes it, and records results."""

    def run(
        self,
        case_id: str,
        project_id: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> RunRecord:
        record = RunRecord(case_id=case_id, project_id=project_id)
        record.status = RunStatus.RUNNING

        initial_state: dict[str, Any] = {
            "case_id": case_id,
            "run_id": record.run_id,
            "status": "running",
        }
        if project_id:
            initial_state["project_id"] = project_id

        try:
            graph = build_workflow()
            compiled = graph.compile()
            final_state = compiled.invoke(initial_state)
            record.status = RunStatus.COMPLETED
            record.result = {
                "refined_checklist": final_state.get("refined_checklist", []),
                "reflection_notes": final_state.get("reflection_notes", ""),
            }
        except Exception as exc:
            logger.exception("Workflow run failed for case '%s'.", case_id)
            record.status = RunStatus.FAILED
            record.error = str(exc)

        record.finished_at = datetime.utcnow()
        return record
