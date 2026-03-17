from __future__ import annotations

import pytest


class FakeLLMClient:
    """测试用 LLM 客户端，返回预定义的结构化响应。

    支持 ResearchOutput、CheckpointDraftCollection 和 DraftCaseCollection 三种模型。
    """

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
                        "fact_id": "FACT-001",
                        "description": "User can log in using SMS verification code",
                        "source_section": "Login Feature",
                        "category": "behavior",
                        "evidence_refs": [
                            {
                                "section_title": "Login Feature",
                                "excerpt": "SMS-based login flow",
                                "line_start": 3,
                                "line_end": 6,
                                "confidence": 0.9,
                            }
                        ],
                    },
                    {
                        "fact_id": "FACT-002",
                        "description": "SMS code expires in 5 minutes",
                        "source_section": "Acceptance Criteria",
                        "category": "constraint",
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
            )

        if response_model.__name__ == "CheckpointDraftCollection":
            return response_model.model_validate(
                {
                    "checkpoints": [
                        {
                            "title": "Verify SMS login success flow",
                            "objective": "User can successfully log in with a valid SMS code",
                            "category": "functional",
                            "risk": "high",
                            "branch_hint": "happy path",
                            "fact_ids": ["FACT-001"],
                            "preconditions": ["User has a registered phone number"],
                        },
                        {
                            "title": "Verify SMS code expiration",
                            "objective": "Expired SMS code should be rejected",
                            "category": "edge_case",
                            "risk": "medium",
                            "branch_hint": "timeout path",
                            "fact_ids": ["FACT-002"],
                            "preconditions": ["User has requested an SMS code"],
                        },
                    ]
                }
            )

        # DraftCaseCollection（默认）
        return response_model.model_validate(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "title": "User logs in with SMS code",
                        "preconditions": ["User has a registered phone number"],
                        "steps": [
                            "Open login page",
                            "Request SMS code",
                            "Submit valid code",
                        ],
                        "expected_results": ["User reaches the dashboard"],
                        "priority": "P1",
                        "category": "functional",
                        "checkpoint_id": "CP-test0001",
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
                        "id": "TC-002",
                        "title": "Expired SMS code is rejected",
                        "preconditions": ["User has requested an SMS code"],
                        "steps": [
                            "Wait for code to expire",
                            "Submit expired code",
                        ],
                        "expected_results": ["Error message is displayed"],
                        "priority": "P1",
                        "category": "edge_case",
                        "checkpoint_id": "CP-test0002",
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
                ]
            }
        )


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()
