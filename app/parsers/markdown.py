from __future__ import annotations

import hashlib
from pathlib import Path

from app.domain.document_models import DocumentSection, DocumentSource, ParsedDocument


class MarkdownParser:
    def parse(self, path: Path) -> ParsedDocument:
        raw_text = path.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
        sections: list[DocumentSection] = []
        current_heading = path.stem
        current_level = 1
        current_start = 1
        current_lines: list[str] = []

        for index, line in enumerate(lines, start=1):
            if line.startswith("#"):
                if current_lines or sections:
                    sections.append(
                        DocumentSection(
                            heading=current_heading,
                            level=current_level,
                            content="\n".join(current_lines).strip(),
                            line_start=current_start,
                            line_end=index - 1,
                        )
                    )
                level = len(line) - len(line.lstrip("#"))
                current_heading = line[level:].strip() or path.stem
                current_level = level
                current_start = index
                current_lines = []
                continue

            current_lines.append(line)

        if lines:
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    level=current_level,
                    content="\n".join(current_lines).strip(),
                    line_start=current_start,
                    line_end=len(lines),
                )
            )

        references = [line.strip() for line in lines if "](" in line]
        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        return ParsedDocument(
            raw_text=raw_text,
            sections=sections,
            references=references,
            metadata={"section_count": len(sections)},
            source=DocumentSource(
                source_path=str(path),
                source_type="markdown",
                title=sections[0].heading if sections else path.stem,
                checksum=checksum,
            ),
        )
