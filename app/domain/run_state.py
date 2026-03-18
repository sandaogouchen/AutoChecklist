"""Run-level bookkeeping that wraps workflow execution metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunRecord(BaseModel):
    """Persistent record of a single workflow invocation."""

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    case_id: str
    project_id: Optional[str] = None  # NEW \u2013 link to project context
    status: RunStatus = RunStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
