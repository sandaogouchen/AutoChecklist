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
            )

        return response_model.model_validate(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "title": "User logs in with SMS code",
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
                    }
                ]
            }
        )


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()
