"""Unit tests for application logging setup."""

from __future__ import annotations

import logging

from app.config.settings import Settings
from app.main import create_app


class _DummyWorkflowService:
    def __init__(self) -> None:
        self.project_context_service = None


def _reset_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    return logger


def test_create_app_configures_application_logging(monkeypatch, tmp_path) -> None:
    called: list[str] = []

    def _fake_configure_app_logging(*, level: str) -> None:
        called.append(level)

    monkeypatch.setattr("app.main.configure_app_logging", _fake_configure_app_logging)

    create_app(
        settings=Settings(output_dir=str(tmp_path)),
        workflow_service=_DummyWorkflowService(),
    )

    assert called == ["INFO"]


def test_configure_app_logging_reuses_uvicorn_handler() -> None:
    from app.logging import configure_app_logging

    app_logger = _reset_logger("app")
    uvicorn_logger = _reset_logger("uvicorn")

    handler = logging.StreamHandler()
    uvicorn_logger.addHandler(handler)

    configure_app_logging(level="INFO")

    assert app_logger.level == logging.INFO
    assert app_logger.propagate is False
    assert app_logger.handlers == [handler]
