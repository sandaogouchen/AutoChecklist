"""Application logging setup helpers."""

from __future__ import annotations

import logging


def configure_app_logging(*, level: str = "INFO") -> None:
    """Ensure ``app.*`` loggers emit to the same console as Uvicorn.

    Reuses Uvicorn's default console handler when available so application
    logs appear in the existing terminal output without introducing a second
    formatting style. Falls back to a plain ``StreamHandler`` outside Uvicorn.
    """
    app_logger = logging.getLogger("app")
    resolved_level = logging._nameToLevel.get(level.upper(), logging.INFO)

    app_logger.setLevel(resolved_level)
    app_logger.propagate = False

    if app_logger.handlers:
        return

    uvicorn_logger = logging.getLogger("uvicorn")
    if uvicorn_logger.handlers:
        app_logger.handlers = list(uvicorn_logger.handlers)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(name)s: %(message)s"))
    app_logger.addHandler(handler)

    # ---- 确保 timing 子 logger 继承 app logger 的配置 ----
    timing_logger = logging.getLogger("app.timing")
    timing_logger.setLevel(resolved_level)
