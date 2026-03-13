from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.document_models import ParsedDocument


class BaseDocumentParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument:
        """Parse a source document into structured sections."""
