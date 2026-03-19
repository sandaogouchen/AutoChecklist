from __future__ import annotations

import re

import pytest


class FakeLLMClient:
    """测试用 LLM 客户端，返回预定义的结构化响应。

    支持 ResearchOutput、CheckpointDraftCollection、DraftCaseCollection，
    以及 checklist 语义归一化所需的两阶段结构化模型。
    """

    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        user_prompt = kwargs.get("user_prompt", "")
        checkpoint_ids = re.findall(r"Checkpoint ID:\s*(CP-[A-Za-z0-9_-]+)", user_prompt)

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

        if response_model.__name__ == "CanonicalOutlineNodeCollection":
            return response_model.model_validate(
                {
                    "canonical_nodes": [
                        {
                            "node_id": "node-login",
                            "semantic_key": "login",
                            "display_text": "短信登录",
                            "kind": "business_object",
                            "visibility": "visible",
                            "aliases": ["SMS login"],
                        },
                        {
                            "node_id": "node-open-login",
                            "semantic_key": "open_login_page",
                            "display_text": "打开登录页",
                            "kind": "page",
                            "visibility": "visible",
                            "aliases": ["Open login page"],
                        },
                        {
                            "node_id": "node-request-code",
                            "semantic_key": "request_sms_code",
                            "display_text": "请求短信验证码",
                            "kind": "action",
                            "visibility": "visible",
                            "aliases": ["Request SMS code"],
                        },
                        {
                            "node_id": "node-submit-valid-code",
                            "semantic_key": "submit_valid_code",
                            "display_text": "提交有效验证码",
                            "kind": "action",
                            "visibility": "visible",
                            "aliases": ["Submit valid code"],
                        },
                        {
                            "node_id": "node-code-expired",
                            "semantic_key": "sms_code_expired",
                            "display_text": "验证码已过期",
                            "kind": "context",
                            "visibility": "visible",
                            "aliases": ["Code expired"],
                        },
                        {
                            "node_id": "node-submit-expired-code",
                            "semantic_key": "submit_expired_code",
                            "display_text": "提交已过期验证码",
                            "kind": "action",
                            "visibility": "visible",
                            "aliases": ["Submit expired code"],
                        },
                    ]
                }
            )

        if response_model.__name__ == "CheckpointPathCollection":
            return response_model.model_validate(
                {
                    "checkpoint_paths": [
                        {
                            "checkpoint_id": checkpoint_ids[0] if checkpoint_ids else "CP-test0001",
                            "path_node_ids": [
                                "node-login",
                                "node-open-login",
                                "node-request-code",
                                "node-submit-valid-code",
                            ],
                        },
                        {
                            "checkpoint_id": checkpoint_ids[1] if len(checkpoint_ids) > 1 else "CP-test0002",
                            "path_node_ids": [
                                "node-login",
                                "node-open-login",
                                "node-code-expired",
                                "node-submit-expired-code",
                            ],
                        },
                    ]
                }
            )

        if response_model.__name__ == "SemanticNodeCollection":
            return response_model.model_validate(
                {
                    "canonical_nodes": [
                        {
                            "node_id": "node-registered-phone",
                            "semantic_key": "registered_phone",
                            "display_text": "用户有已注册手机号",
                            "kind": "precondition",
                            "hidden": False,
                            "aliases": ["User has a registered phone number"],
                        },
                        {
                            "node_id": "node-open-login",
                            "semantic_key": "open_login_page",
                            "display_text": "打开登录页",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Open login page"],
                        },
                        {
                            "node_id": "node-request-code",
                            "semantic_key": "request_sms_code",
                            "display_text": "请求短信验证码",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Request SMS code"],
                        },
                        {
                            "node_id": "node-submit-valid-code",
                            "semantic_key": "submit_valid_code",
                            "display_text": "提交有效验证码",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Submit valid code"],
                        },
                        {
                            "node_id": "node-requested-code",
                            "semantic_key": "requested_sms_code",
                            "display_text": "用户已请求短信验证码",
                            "kind": "precondition",
                            "hidden": False,
                            "aliases": ["User has requested an SMS code"],
                        },
                        {
                            "node_id": "node-wait-expire",
                            "semantic_key": "wait_until_expired",
                            "display_text": "等待验证码过期",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Wait for code to expire"],
                        },
                        {
                            "node_id": "node-submit-expired-code",
                            "semantic_key": "submit_expired_code",
                            "display_text": "提交已过期验证码",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Submit expired code"],
                        },
                    ]
                }
            )

        if response_model.__name__ == "SemanticPathCollection":
            return response_model.model_validate(
                {
                    "semantic_paths": [
                        {
                            "test_case_id": "TC-001",
                            "path_node_ids": [
                                "node-registered-phone",
                                "node-open-login",
                                "node-request-code",
                                "node-submit-valid-code",
                            ],
                            "expected_results": ["User reaches the dashboard"],
                        },
                        {
                            "test_case_id": "TC-002",
                            "path_node_ids": [
                                "node-requested-code",
                                "node-wait-expire",
                                "node-submit-expired-code",
                            ],
                            "expected_results": ["Error message is displayed"],
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
                        "checkpoint_id": checkpoint_ids[0] if checkpoint_ids else "CP-test0001",
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
                        "checkpoint_id": checkpoint_ids[1] if len(checkpoint_ids) > 1 else "CP-test0002",
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


class FakeLLMClientLowQuality:
    """测试用 LLM 客户端，返回低质量的结构化响应。

    生成的测试用例缺少 evidence_refs、steps 或 expected_results，
    用于测试迭代评估回路的回流能力。
    """

    def __init__(self) -> None:
        self._call_count = 0

    def generate_structured(self, **kwargs):
        self._call_count += 1
        response_model = kwargs["response_model"]

        if response_model.__name__ == "ResearchOutput":
            return response_model(
                feature_topics=["Login", "Registration"],
                user_scenarios=["User logs in"],
                constraints=["Password must be 8+ chars"],
                ambiguities=[],
                test_signals=[],
                facts=[
                    {
                        "fact_id": "FACT-001",
                        "description": "User can log in",
                        "source_section": "Login",
                        "category": "behavior",
                        "evidence_refs": [
                            {
                                "section_title": "Login Feature",
                                "excerpt": "Login flow",
                                "line_start": 3,
                                "line_end": 6,
                                "confidence": 0.9,
                            }
                        ],
                    },
                    {
                        "fact_id": "FACT-002",
                        "description": "User can register",
                        "source_section": "Registration",
                        "category": "behavior",
                        "evidence_refs": [],
                    },
                    {
                        "fact_id": "FACT-003",
                        "description": "Password validation",
                        "source_section": "Security",
                        "category": "constraint",
                        "evidence_refs": [],
                    },
                ],
            )

        if response_model.__name__ == "CheckpointDraftCollection":
            # 只覆盖部分 fact，故意留下 gap
            return response_model.model_validate(
                {
                    "checkpoints": [
                        {
                            "title": "Verify basic login",
                            "objective": "User can log in",
                            "category": "functional",
                            "risk": "high",
                            "fact_ids": ["FACT-001"],
                            "preconditions": [],
                        },
                    ]
                }
            )

        if response_model.__name__ == "CanonicalOutlineNodeCollection":
            return response_model.model_validate(
                {
                    "canonical_nodes": [
                        {
                            "node_id": "node-login",
                            "semantic_key": "login",
                            "display_text": "短信登录",
                            "kind": "business_object",
                            "visibility": "visible",
                            "aliases": ["SMS login"],
                        },
                        {
                            "node_id": "node-open-page",
                            "semantic_key": "open_page",
                            "display_text": "打开页面",
                            "kind": "page",
                            "visibility": "visible",
                            "aliases": ["Open page"],
                        },
                        {
                            "node_id": "node-click-login",
                            "semantic_key": "click_login",
                            "display_text": "点击登录",
                            "kind": "action",
                            "visibility": "visible",
                            "aliases": ["Click login"],
                        },
                    ]
                }
            )

        if response_model.__name__ == "CheckpointPathCollection":
            return response_model.model_validate(
                {
                    "checkpoint_paths": [
                        {
                            "checkpoint_id": checkpoint_ids[0] if checkpoint_ids else "CP-test0001",
                            "path_node_ids": [
                                "node-login",
                                "node-open-page",
                                "node-click-login",
                            ],
                        }
                    ]
                }
            )

        if response_model.__name__ == "SemanticNodeCollection":
            return response_model.model_validate(
                {
                    "canonical_nodes": [
                        {
                            "node_id": "node-open-page",
                            "semantic_key": "open_page",
                            "display_text": "打开页面",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Open page"],
                        },
                        {
                            "node_id": "node-click-login",
                            "semantic_key": "click_login",
                            "display_text": "点击登录",
                            "kind": "action",
                            "hidden": False,
                            "aliases": ["Click login"],
                        },
                    ]
                }
            )

        if response_model.__name__ == "SemanticPathCollection":
            return response_model.model_validate(
                {
                    "semantic_paths": [
                        {
                            "test_case_id": "TC-001",
                            "path_node_ids": ["node-open-page", "node-click-login"],
                            "expected_results": [],
                        }
                    ]
                }
            )

        # DraftCaseCollection - 返回低质量用例
        return response_model.model_validate(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "title": "Login test",
                        "preconditions": [],
                        "steps": ["Open page", "Click login"],
                        "expected_results": [],  # 故意缺少预期结果
                        "priority": "P2",
                        "category": "functional",
                        "checkpoint_id": "",  # 故意缺少 checkpoint_id
                        "evidence_refs": [],  # 故意缺少 evidence
                    },
                ]
            }
        )


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def fake_llm_client_low_quality() -> FakeLLMClientLowQuality:
    return FakeLLMClientLowQuality()
