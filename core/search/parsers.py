"""Parse uploaded files to plain text."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path


@dataclass
class ParsedDocument:
    title: str
    content: str
    source_type: str
    metadata: dict = field(default_factory=dict)


def parse_file(data: bytes, filename: str) -> ParsedDocument:
    suffix = Path(filename).suffix.lower()
    title = Path(filename).stem

    if suffix in (".txt", ".md", ".markdown"):
        text = data.decode("utf-8", errors="replace")
        return ParsedDocument(title=title, content=text, source_type=suffix.lstrip("."))

    if suffix == ".pdf":
        return _parse_pdf(data, title)

    if suffix in (".docx",):
        return _parse_docx(data, title)

    raise ValueError(f"Unsupported file type: {suffix}. Supported: .txt, .md, .pdf, .docx")


def _parse_pdf(data: bytes, title: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("Install pypdf: pip install pypdf") from exc

    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text.strip()}")

    content = "\n\n".join(pages)
    if not content.strip():
        raise ValueError("PDF has no extractable text (scanned image?)")

    return ParsedDocument(
        title=title,
        content=content,
        source_type="pdf",
        metadata={"page_count": len(reader.pages)},
    )


def _parse_docx(data: bytes, title: str) -> ParsedDocument:
    try:
        from docx import Document
    except ImportError as exc:
        raise ImportError("Install python-docx: pip install python-docx") from exc

    doc = Document(BytesIO(data))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    content = "\n\n".join(paragraphs)
    if not content.strip():
        raise ValueError("DOCX has no text content")

    return ParsedDocument(
        title=title,
        content=content,
        source_type="docx",
        metadata={"paragraph_count": len(paragraphs)},
    )
