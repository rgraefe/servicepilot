"""Deterministic preflight parsing for the version-controlled knowledge corpus.

Production retrieval is handled by Google Agent Search.  This module mirrors the
important hierarchy contract locally: every leaf chunk carries its complete
ancestor heading path so a retrieved paragraph never loses its section context.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re


HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class KnowledgeChunk:
    document_id: str
    chunk_id: str
    heading_path: tuple[str, ...]
    text: str

    @property
    def retrieval_text(self) -> str:
        return f"{' > '.join(self.heading_path)}\n\n{self.text}"


def parse_markdown(document_id: str, source: str) -> list[KnowledgeChunk]:
    """Split Markdown into leaf paragraphs while retaining ancestor headings."""
    headings: list[str] = []
    paragraphs: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            paragraphs.append(" ".join(line.strip() for line in current).strip())
            current.clear()

    records: list[tuple[tuple[str, ...], str]] = []
    for raw_line in source.splitlines():
        match = HEADING.match(raw_line)
        if match:
            flush()
            for paragraph in paragraphs:
                records.append((tuple(headings), paragraph))
            paragraphs.clear()
            level = len(match.group(1))
            headings[level - 1 :] = [match.group(2)]
        elif raw_line.strip():
            current.append(raw_line)
        else:
            flush()
    flush()
    for paragraph in paragraphs:
        records.append((tuple(headings), paragraph))

    chunks: list[KnowledgeChunk] = []
    for index, (heading_path, text) in enumerate(records, start=1):
        if not heading_path:
            raise ValueError(f"{document_id}: content before first heading")
        digest = sha256(
            f"{document_id}|{'/'.join(heading_path)}|{index}|{text}".encode("utf-8")
        ).hexdigest()[:16]
        chunks.append(
            KnowledgeChunk(
                document_id=document_id,
                chunk_id=f"{document_id}-{digest}",
                heading_path=heading_path,
                text=text,
            )
        )
    return chunks


def parse_markdown_file(document_id: str, path: Path) -> list[KnowledgeChunk]:
    return parse_markdown(document_id, path.read_text(encoding="utf-8"))
