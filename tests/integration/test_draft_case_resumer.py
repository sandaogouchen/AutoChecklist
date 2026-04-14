from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.config.settings import Settings
from app.domain.api_models import CaseGenerationRequest
from app.repositories.run_repository import FileRunRepository
from app.services.draft_case_resumer import resume_run_from_saved_draft_cases
from app.services.workflow_service import WorkflowService


def test_resume_run_from_saved_draft_cases_continues_main_flow(
    tmp_path: Path,
    fake_llm_client,
) -> None:
    draft_cases_path = tmp_path / "draft_cases.json"
    draft_cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "TC-CP-f9989d97-01",
                    "title": "Injected SMS login success case",
                    "preconditions": ["User has a registered phone number"],
                    "steps": [
                        "Open login page",
                        "Request SMS code",
                        "Submit valid code",
                    ],
                    "expected_results": ["User reaches the dashboard"],
                    "priority": "P0",
                    "category": "functional",
                    "checkpoint_id": "CP-f9989d97",
                    "evidence_refs": [
                        {
                            "section_title": "Acceptance Criteria",
                            "excerpt": "Successful login redirects to the dashboard.",
                            "line_start": 7,
                            "line_end": 10,
                            "confidence": 0.9,
                        }
                    ],
                },
                {
                    "id": "TC-CP-813b8af5-01",
                    "title": "Injected SMS code expired case",
                    "preconditions": ["User has requested an SMS code"],
                    "steps": [
                        "Wait for code to expire",
                        "Submit expired code",
                    ],
                    "expected_results": ["Error message is displayed"],
                    "priority": "P1",
                    "category": "edge_case",
                    "checkpoint_id": "CP-813b8af5",
                    "evidence_refs": [
                        {
                            "section_title": "Acceptance Criteria",
                            "excerpt": "Code validity period is 5 minutes",
                            "line_start": 7,
                            "line_end": 10,
                            "confidence": 0.85,
                        }
                    ],
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
    )
    request = CaseGenerationRequest(
        file_path=str(Path("tests/fixtures/sample_prd.md").resolve())
    )

    run = resume_run_from_saved_draft_cases(
        service=service,
        request=request,
        draft_cases_path=draft_cases_path,
    )

    assert run.status == "succeeded"
    assert len(run.test_cases) == 2
    assert "Injected SMS code expired case" in [case.title for case in run.test_cases]
    assert any("Injected SMS" in case.title for case in run.test_cases)
    assert "xmind_file" in run.artifacts
    assert "test_cases_markdown" in run.artifacts

    markdown = Path(run.artifacts["test_cases_markdown"]).read_text(encoding="utf-8")
    assert "短信登录" in markdown
    assert "提交有效验证码" in markdown
    assert "User reaches the dashboard" in markdown
    assert "Error message is displayed" in markdown

    with zipfile.ZipFile(run.artifacts["xmind_file"], "r") as zf:
        content = json.loads(zf.read("content.json"))

    serialized = json.dumps(content[0]["rootTopic"], ensure_ascii=False)
    assert "短信登录" in serialized
    assert "提交有效验证码" in serialized
    assert "User reaches the dashboard" in serialized
    assert "Error message is displayed" in serialized
