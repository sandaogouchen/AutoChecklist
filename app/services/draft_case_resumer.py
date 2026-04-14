from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun
from app.domain.case_models import TestCase
from app.graphs import case_generation as case_generation_module
from app.services.workflow_service import WorkflowService


def resume_run_from_saved_draft_cases(
    *,
    service: WorkflowService,
    request: CaseGenerationRequest,
    draft_cases_path: str | Path,
) -> CaseGenerationRun:
    draft_cases = _load_draft_cases(draft_cases_path)
    with _inject_draft_writer(draft_cases):
        return service.create_run(request)


def _load_draft_cases(draft_cases_path: str | Path) -> list[TestCase]:
    path = Path(draft_cases_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [TestCase.model_validate(item) for item in payload]


@contextmanager
def _inject_draft_writer(draft_cases: list[TestCase]) -> Iterator[None]:
    original = case_generation_module.DraftWriterNode

    class _InjectedDraftWriter:
        def __init__(self, _llm_client) -> None:
            self._draft_cases = [case.model_copy(deep=True) for case in draft_cases]

        def __call__(self, _state):
            return {"draft_cases": [case.model_copy(deep=True) for case in self._draft_cases]}

    case_generation_module.DraftWriterNode = _InjectedDraftWriter
    try:
        yield
    finally:
        case_generation_module.DraftWriterNode = original
