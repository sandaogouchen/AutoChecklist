"""知识文档接入模块。

负责从本地目录加载 Markdown 知识文档，提取元数据，
并交由 GraphRAG 引擎进行索引。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.knowledge.models import KnowledgeDocument

logger = logging.getLogger(__name__)


def scan_knowledge_directory(
    docs_dir: str,
    max_doc_size_kb: int = 1024,
) -> list[tuple[KnowledgeDocument, str]]:
    """扫描知识文档目录，加载所有符合条件的 Markdown 文件。

    递归扫描指定目录下的所有 .md 文件，过滤掉空文件、超大文件和
    非 UTF-8 编码文件。

    Args:
        docs_dir: 知识文档根目录路径。
        max_doc_size_kb: 单个文档最大 KB 数，超过则跳过。

    Returns:
        (KnowledgeDocument 元数据, 文档内容文本) 的列表。
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning("知识文档目录不存在: %s", docs_dir)
        return []

    if not docs_path.is_dir():
        logger.warning("知识文档路径不是目录: %s", docs_dir)
        return []

    results: list[tuple[KnowledgeDocument, str]] = []
    max_size_bytes = max_doc_size_kb * 1024

    for md_file in sorted(docs_path.rglob("*.md")):
        if not md_file.is_file():
            continue

        file_size = md_file.stat().st_size
        if file_size == 0:
            logger.warning("跳过空文件: %s", md_file)
            continue

        if file_size > max_size_bytes:
            logger.warning(
                "跳过超大文件 (%d KB > %d KB): %s",
                file_size // 1024,
                max_doc_size_kb,
                md_file,
            )
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("跳过非 UTF-8 编码文件: %s", md_file)
            continue
        except OSError as exc:
            logger.warning("读取文件失败 (%s): %s", exc, md_file)
            continue

        md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        doc_id = f"doc_{md5_hash[:12]}"

        doc = KnowledgeDocument(
            doc_id=doc_id,
            file_name=md_file.name,
            file_path=str(md_file),
            file_size_bytes=file_size,
            md5_hash=md5_hash,
        )
        results.append((doc, content))

    logger.info("从 %s 扫描到 %d 个有效知识文档", docs_dir, len(results))
    return results


def validate_document_path(file_path: str, max_doc_size_kb: int = 1024) -> str:
    """校验单个文档路径的合法性，返回文件内容。

    Args:
        file_path: 文档文件路径。
        max_doc_size_kb: 最大文件大小（KB）。

    Returns:
        文档内容文本。

    Raises:
        ValueError: 文件不存在、格式不符、编码错误或超出大小限制。
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise ValueError(f"文件不存在: {file_path}")

    if path.suffix.lower() != ".md":
        raise ValueError(f"仅支持 .md 格式文件: {file_path}")

    file_size = path.stat().st_size
    if file_size == 0:
        raise ValueError(f"文件为空: {file_path}")

    max_size_bytes = max_doc_size_kb * 1024
    if file_size > max_size_bytes:
        raise ValueError(
            f"文件过大 ({file_size // 1024} KB > {max_doc_size_kb} KB): {file_path}"
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"文件编码不是 UTF-8: {file_path}") from exc

    return content
