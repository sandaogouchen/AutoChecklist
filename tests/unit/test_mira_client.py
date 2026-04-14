from __future__ import annotations

import asyncio
import json
import logging

import pytest

from app.clients.mira_client import MiraClient, MiraClientConfig


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncClient:
    last_request: dict[str, object] | None = None

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None

    def stream(self, method, url, headers=None, json=None):
        self.__class__.last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }
        return _FakeAsyncStreamResponse(
            [
                'data: {"delta":{"content":"hello"}}',
                'data: {"messageId":"msg-1","content":"hello","roundIndex":1}',
            ]
        )


async def _yield_events(events):
    for event in events:
        yield event


def test_mira_client_create_session_extracts_session_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "data": {
                    "sessionItem": {
                        "sessionId": "session-123",
                    }
                }
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    session_id = client.create_session(
        topic="autochecklist",
        model="mira-model",
        data_sources=[{"key": "manus"}],
    )

    assert session_id == "session-123"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://mira.example.com/mira/api/v1/chat/create"
    assert captured["headers"]["Cookie"] == "mira_session=jwt-token"
    assert "jwt-token" not in captured["headers"]
    assert captured["json"]["sessionProperties"]["topic"] == "autochecklist"
    assert captured["json"]["sessionProperties"]["model"] == "mira-model"
    assert captured["json"]["sessionProperties"]["dataSource"] == {"key": "manus"}
    assert captured["json"]["sessionProperties"]["dataSources"] == [{"key": "manus"}]


def test_mira_client_uses_full_cookie_header_when_configured(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "data": {
                    "sessionItem": {
                        "sessionId": "session-cookie-1",
                    }
                }
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="",
            session_cookie="locale=zh-CN; mira_session=session-token",
            client_version="0.61.0_extension",
        )
    )

    session_id = client.create_session(
        topic="autochecklist",
        model="gpt-5.4",
        data_sources=[{"key": "manus"}],
    )

    assert session_id == "session-cookie-1"
    assert captured["headers"]["Cookie"] == "locale=zh-CN; mira_session=session-token"
    assert "jwt-token" not in captured["headers"]
    assert captured["headers"]["x-mira-client"] == "0.61.0_extension"


def test_mira_client_send_message_sync_prefers_final_content(monkeypatch) -> None:
    async def _fake_collect_stream(self, session_id, content, config=None):
        del self, session_id, content, config
        return [
            {"delta": {"content": "hello "}},
            {"delta": {"content": "world"}},
            {"messageId": "msg-1", "content": '{"status":"ok"}', "roundIndex": 2},
        ]

    monkeypatch.setattr(MiraClient, "_collect_stream", _fake_collect_stream)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    response = client.send_message_sync("session-1", "prompt")

    assert response.message_id == "msg-1"
    assert response.round_index == 2
    assert response.content == '{"status":"ok"}'


def test_mira_client_send_message_sync_extracts_nested_message_content(monkeypatch) -> None:
    async def _fake_collect_stream(self, session_id, content, config=None):
        del self, session_id, content, config
        return [
            {"event": "message_start"},
            {
                "event": "message_end",
                "data": {
                    "message": {
                        "messageId": "msg-nested-1",
                        "roundIndex": 3,
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"status":"ok"}',
                            }
                        ],
                    }
                },
            },
        ]

    monkeypatch.setattr(MiraClient, "_collect_stream", _fake_collect_stream)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    response = client.send_message_sync("session-1", "prompt")

    assert response.message_id == "msg-nested-1"
    assert response.round_index == 3
    assert response.content == '{"status":"ok"}'


def test_mira_client_send_message_sync_falls_back_to_nested_delta_fragments(monkeypatch) -> None:
    async def _fake_collect_stream(self, session_id, content, config=None):
        del self, session_id, content, config
        return [
            {
                "event": "content_delta",
                "data": {
                    "delta": {
                        "content": [
                            {"type": "text", "text": '{"status":"'}
                        ]
                    }
                },
            },
            {
                "event": "content_delta",
                "data": {
                    "delta": {
                        "content": [
                            {"type": "text", "text": 'ok"}'}
                        ]
                    }
                },
            },
        ]

    monkeypatch.setattr(MiraClient, "_collect_stream", _fake_collect_stream)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    response = client.send_message_sync("session-1", "prompt")

    assert response.content == '{"status":"ok"}'


def test_mira_client_collect_stream_unwraps_enveloped_events(monkeypatch) -> None:
    async def _fake_send_message_stream(self, session_id, content, config=None):
        del self, session_id, content, config
        async for event in _yield_events(
            [
                {
                    "e": '{"event":"content_delta","data":{"delta":{"content":[{"type":"text","text":"hello"}]}}}'
                },
                {"done": True},
            ]
        ):
            yield event

    monkeypatch.setattr(MiraClient, "send_message_stream", _fake_send_message_stream)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    events = asyncio.run(client._collect_stream("session-1", "prompt"))

    assert events == [
        {
            "event": "content_delta",
            "data": {
                "delta": {
                    "content": [{"type": "text", "text": "hello"}]
                }
            },
        }
    ]


def test_mira_client_send_message_sync_polls_messages_after_finish_without_content(
    monkeypatch,
) -> None:
    async def _fake_send_message_stream(self, session_id, content, config=None):
        del self, session_id, content, config
        async for event in _yield_events(
            [
                {
                    "e": '{"event":"finish","data":{},"timestamp":1775759015916}'
                },
                {"done": True},
            ]
        ):
            yield event

    monkeypatch.setattr(MiraClient, "send_message_stream", _fake_send_message_stream)
    monkeypatch.setattr("app.clients.mira_client.time.sleep", lambda _seconds: None)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    poll_calls: list[str] = []

    def _fake_get_messages(session_id, *, start_round=None, end_round=None):
        del start_round, end_round
        poll_calls.append(session_id)
        return [
            {
                "messageId": "msg-user-1",
                "sender": "user",
                "content": "prompt",
                "roundIndex": 1,
            },
            {
                "messageId": "msg-assistant-1",
                "sender": "assistant",
                "content": '{"status":"ok"}',
                "roundIndex": 1,
            },
        ]

    monkeypatch.setattr(client, "get_messages", _fake_get_messages)

    response = client.send_message_sync("session-1", "prompt")

    assert response.message_id == "msg-assistant-1"
    assert response.round_index == 1
    assert response.content == '{"status":"ok"}'
    assert poll_calls == ["session-1"]


def test_mira_client_select_assistant_message_prefers_numeric_assistant_sender_and_latest() -> None:
    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    response = client._select_assistant_message(
        [
            {
                "messageId": "msg-user",
                "sender": 1,
                "content": "user prompt",
                "roundIndex": 1,
                "sequence": 1,
                "timestamp": 1000,
            },
            {
                "messageId": "msg-assistant-new",
                "sender": 2,
                "content": '{"status":"new"}',
                "roundIndex": 1,
                "sequence": 3,
                "timestamp": 3000,
            },
            {
                "messageId": "msg-assistant-old",
                "sender": 2,
                "content": '{"status":"old"}',
                "roundIndex": 1,
                "sequence": 2,
                "timestamp": 2000,
            },
        ]
    )

    assert response is not None
    assert response.message_id == "msg-assistant-new"
    assert response.content == '{"status":"new"}'


def test_mira_client_send_message_stream_includes_summary_agent_and_comprehensive(
    monkeypatch,
) -> None:
    _FakeAsyncClient.last_request = None
    monkeypatch.setattr("app.clients.mira_client.httpx.AsyncClient", _FakeAsyncClient)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
            default_model="gpt-5.4",
        )
    )

    events = asyncio.run(
        client._collect_stream(
            "session-1",
            "prompt",
            {"mode": "quick"},
        )
    )

    assert len(events) == 2
    assert _FakeAsyncClient.last_request is not None
    assert _FakeAsyncClient.last_request["json"] == {
        "sessionId": "session-1",
        "content": "prompt",
        "messageType": 1,
        "summaryAgent": "gpt-5.4",
        "dataSources": [],
        "comprehensive": 0,
        "config": {"mode": "quick"},
    }


def test_mira_client_create_session_accepts_nested_session_wrappers(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del method, url, headers, timeout, kwargs
        return _FakeResponse(
            {
                "code": 0,
                "msg": "ok",
                "data": {
                    "session": {
                        "sessionItem": {
                            "sessionId": "session-nested-1",
                        }
                    }
                },
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    assert client.create_session(topic="autochecklist") == "session-nested-1"


def test_mira_client_create_session_loads_default_data_source_from_web_configs(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del headers, timeout
        calls.append((method, url, kwargs))
        if url.endswith("/global_config/web_configs"):
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "dataSources": [
                            {"key": "manus", "enable": True},
                            {"key": "disabled", "enable": False},
                        ]
                    },
                }
            )
        return _FakeResponse(
            {
                "code": 0,
                "data": {
                    "sessionItem": {
                        "sessionId": "session-default-datasource-1",
                    }
                },
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    session_id = client.create_session(topic="autochecklist", model="mira-model", data_sources=[])

    assert session_id == "session-default-datasource-1"
    assert calls[0][0] == "GET"
    assert calls[0][1] == "https://mira.example.com/global_config/web_configs"
    assert calls[1][0] == "POST"
    assert calls[1][2]["json"]["sessionProperties"]["dataSource"] == {"key": "manus"}
    assert calls[1][2]["json"]["sessionProperties"]["dataSources"] == [{"key": "manus"}]


def test_mira_client_create_session_retries_with_fallback_payload(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del method, url, headers, timeout
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _FakeResponse(
                {
                    "code": 4001,
                    "msg": "invalid sessionProperties.dataSource",
                    "log_id": "log-1",
                }
            )
        return _FakeResponse(
            {
                "code": 0,
                "data": {
                    "sessionItem": {
                        "sessionId": "session-fallback-1",
                    }
                },
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    assert (
        client.create_session(
            topic="autochecklist",
            model="mira-model",
            data_sources=[{"key": "manus"}],
        )
        == "session-fallback-1"
    )
    assert calls[0]["sessionProperties"]["dataSource"] == {"key": "manus"}
    assert "dataSource" not in calls[1]["sessionProperties"]


def test_mira_client_create_session_falls_back_to_flat_payload_after_session_invalid(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del method, url, headers, timeout
        calls.append(kwargs["json"])
        if len(calls) <= 3:
            return _FakeResponse(
                {
                    "code": 20001,
                    "msg": "session invalid",
                    "log_id": f"log-{len(calls)}",
                }
            )
        return _FakeResponse(
            {
                "code": 0,
                "data": {
                    "sessionItem": {
                        "sessionId": "session-flat-1",
                    }
                },
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    assert (
        client.create_session(
            topic="autochecklist",
            model="mira-model",
            data_sources=[{"key": "manus"}],
        )
        == "session-flat-1"
    )
    assert all("sessionProperties" in call for call in calls[:3])
    assert "sessionProperties" not in calls[3]
    assert calls[3]["topic"] == "autochecklist"
    assert calls[3]["model"] == "mira-model"


def test_mira_client_create_session_surfaces_biz_error_details(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del method, url, headers, timeout, kwargs
        return _FakeResponse(
            {
                "code": 4002,
                "msg": "missing datasource",
                "log_id": "log-xyz",
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    with pytest.raises(ValueError, match="missing datasource"):
        client.create_session(topic="autochecklist")


def test_mira_client_create_session_reports_empty_role_context_for_session_invalid(
    monkeypatch,
) -> None:
    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del headers, timeout, kwargs
        if url.endswith("/global_config/web_configs"):
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "dataSources": [{"key": "manus", "enable": True}],
                    },
                }
            )
        if url.endswith("/devops/get_role"):
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "employeeNumber": "",
                        "name": "",
                        "email": "",
                        "userId": "",
                        "openId": "",
                    },
                }
            )
        assert method == "POST"
        return _FakeResponse(
            {
                "code": 20001,
                "msg": "session invalid",
                "log_id": "log-empty-role",
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    with pytest.raises(ValueError, match="role context.*devops/get_role"):
        client.create_session(topic="autochecklist", model="mira-model", data_sources=[])


def test_mira_client_logs_create_session_attempts(caplog, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _fake_request(method, url, headers=None, timeout=None, **kwargs):
        del method, url, headers, timeout
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _FakeResponse(
                {
                    "code": 20001,
                    "msg": "session invalid",
                    "log_id": "log-1",
                }
            )
        return _FakeResponse(
            {
                "code": 0,
                "data": {
                    "sessionItem": {
                        "sessionId": "session-log-1",
                    }
                },
            }
        )

    monkeypatch.setattr("app.clients.mira_client.httpx.request", _fake_request)

    client = MiraClient(
        MiraClientConfig(
            base_url="https://mira.example.com",
            jwt_token="jwt-token",
        )
    )

    with caplog.at_level(logging.INFO, logger="app.clients.mira_client"):
        session_id = client.create_session(
            topic="autochecklist",
            model="mira-model",
            data_sources=[{"key": "manus"}],
        )

    assert session_id == "session-log-1"
    assert "Mira create_session attempt=1" in caplog.text
    assert "variant=wrapped_with_datasource" in caplog.text
    assert "Mira create_session business error" in caplog.text
    assert "code=20001" in caplog.text
    assert "Mira create_session succeeded" in caplog.text
