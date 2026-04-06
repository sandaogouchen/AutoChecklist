from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.services.coco_response_validator import CocoResponseValidator


class _SimpleSchema(BaseModel):
    value: str = ""


class _SyncLLM:
    def chat(self, prompt: str) -> str:
        del prompt
        return '{"value":"fixed"}'


def test_coco_response_validator_supports_sync_llm_client() -> None:
    validator = CocoResponseValidator(_SyncLLM())

    model, meta = asyncio.run(
        validator.validate_and_fix(
            raw_text="not json",
            schema_class=_SimpleSchema,
            context="sync llm fallback",
        )
    )

    assert model.value == "fixed"
    assert meta["layer"] == "3-full"
