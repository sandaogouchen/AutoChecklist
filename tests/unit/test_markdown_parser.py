from pathlib import Path

from app.parsers.factory import get_parser


def test_markdown_parser_extracts_sections() -> None:
    parser = get_parser(Path("tests/fixtures/sample_prd.md"))
    parsed = parser.parse(Path("tests/fixtures/sample_prd.md"))

    assert parsed.sections
    assert parsed.sections[0].heading == "Login Flow"
