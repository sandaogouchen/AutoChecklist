from __future__ import annotations

import pytest


class FakeLLMClient:
    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        if response_model.__name__ == "ResearchOutput":
            return response_model(
                feature_topics=["Login"],
                user_scenarios=["User logs in with SMS code"],
                constraints=["SMS code expires in 5 minutes"],
                ambiguities=[],
                test_signals=["success path"],
                facts=[
                    {
                        "id": "FACT-001",
                        "summary": "User can log in with SMS code",
                        "change_type": "behavior",
                        "requirement": "Successful login redirects to the dashboard",
                        "branch_hint": "main",
                        "evidence_refs": [
                            {
                                "section_title": "Acceptance Criteria",
                                "excerpt": "Successful login redirects to the dashboard.",
                                "line_start": 7,
                                "line_end": 10,
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
            )

        return response_model.model_validate(
            {
                "test_cases": [
                    {
                        "id": "ROOT-001",
                        "fact_id": "FACT-001",
                        "node_type": "root",
                        "title": "User logs in with SMS code",
                        "branch": "main",
                        "parent": None,
                        "root": None,
                        "prev": None,
                        "next": None,
                        "preconditions": ["User has a registered phone number"],
                        "steps": ["Open login page", "Request SMS code", "Submit valid code"],
                        "expected_results": ["User reaches the dashboard"],
                        "priority": "P1",
                        "category": "functional",
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
                        "id": "",
                        "fact_id": "FACT-001",
                        "node_type": "check",
                        "title": "Expired SMS codes are rejected",
                        "branch": "main",
                        "parent": "ROOT-001",
                        "root": "ROOT-001",
                        "prev": None,
                        "next": None,
                        "preconditions": ["User has requested a code earlier"],
                        "steps": ["Submit an expired SMS code"],
                        "expected_results": ["The login attempt is rejected"],
                        "priority": "P1",
                        "category": "functional",
                        "evidence_refs": [
                            {
                                "section_title": "Acceptance Criteria",
                                "excerpt": "Expired SMS codes are rejected.",
                                "line_start": 7,
                                "line_end": 10,
                                "confidence": 0.9,
                            }
                        ],
                    }
                ]
            }
        )


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()
