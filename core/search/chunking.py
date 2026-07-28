"""Text chunking — split documents for RAG with quality metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import get_settings

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_PARAGRAPH = re.compile(r"\n\s*\n+")


@dataclass
class TextChunk:
    index: int
    content: str
    char_count: int
    token_estimate: int
    start_char: int
    end_char: int
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkAnalysis:
    chunk_count: int
    min_chars: int
    max_chars: int
    avg_chars: float
    min_tokens: int
    max_tokens: int
    avg_tokens: float
    overlap_chars: int
    warnings: list[str] = field(default_factory=list)
    quality_score: float = 1.0  # 0-1, heuristic


def _estimate_tokens(text: str) -> int:
    # Rough: ~4 chars per token for mixed VN/EN
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    metadata: dict | None = None,
) -> list[TextChunk]:
    """Split text into overlapping chunks, preferring paragraph/sentence boundaries."""
    settings = get_settings()
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    if overlap >= size:
        overlap = size // 5

    paragraphs = [p.strip() for p in _PARAGRAPH.split(text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    units: list[str] = []
    for para in paragraphs:
        if len(para) <= size:
            units.append(para)
        else:
            units.extend(_split_sentences(para) or [para])

    chunks: list[TextChunk] = []
    buffer = ""
    buffer_start = 0
    cursor = 0
    idx = 0

    for unit in units:
        candidate = f"{buffer} {unit}".strip() if buffer else unit
        if len(candidate) <= size:
            if not buffer:
                buffer_start = cursor
            buffer = candidate
            cursor += len(unit) + 1
            continue

        if buffer:
            chunks.append(_make_chunk(idx, buffer, buffer_start, metadata))
            idx += 1
            tail = buffer[-overlap:] if overlap and len(buffer) > overlap else ""
            buffer = f"{tail} {unit}".strip() if tail else unit
            buffer_start = cursor - len(tail) if tail else cursor
        else:
            # Unit itself too long — hard split
            start = 0
            while start < len(unit):
                piece = unit[start : start + size]
                chunks.append(_make_chunk(idx, piece, cursor + start, metadata))
                idx += 1
                start += size - overlap if overlap else size
            buffer = ""
        cursor += len(unit) + 1

    if buffer.strip():
        chunks.append(_make_chunk(idx, buffer.strip(), buffer_start, metadata))

    return chunks


def _make_chunk(index: int, content: str, start_char: int, metadata: dict | None) -> TextChunk:
    return TextChunk(
        index=index,
        content=content,
        char_count=len(content),
        token_estimate=_estimate_tokens(content),
        start_char=start_char,
        end_char=start_char + len(content),
        metadata=dict(metadata or {}),
    )


def analyze_chunks(chunks: list[TextChunk], *, overlap_chars: int | None = None) -> ChunkAnalysis:
    """Heuristic quality check — dùng trước khi ingest."""
    settings = get_settings()
    overlap = overlap_chars if overlap_chars is not None else settings.chunk_overlap

    if not chunks:
        return ChunkAnalysis(
            chunk_count=0, min_chars=0, max_chars=0, avg_chars=0,
            min_tokens=0, max_tokens=0, avg_tokens=0, overlap_chars=overlap,
            warnings=["No chunks produced"],
            quality_score=0.0,
        )

    chars = [c.char_count for c in chunks]
    tokens = [c.token_estimate for c in chunks]
    warnings: list[str] = []

    min_c, max_c = min(chars), max(chars)
    avg_c = sum(chars) / len(chars)

    for i, c in enumerate(chunks):
        if c.char_count < 80:
            warnings.append(f"Chunk {i}: quá ngắn ({c.char_count} chars) — có thể thiếu ngữ cảnh")
        if c.char_count > settings.chunk_size * 1.5:
            warnings.append(f"Chunk {i}: quá dài ({c.char_count} chars) — cân nhắc giảm chunk_size")
        if c.content.count("\n") > 15:
            warnings.append(f"Chunk {i}: nhiều dòng — có thể gộp paragraph chưa tốt")

    if max_c > min_c * 3 and len(chunks) > 2:
        warnings.append("Độ dài chunk chênh lệch lớn — cân nhắc chỉnh chunk_size/overlap")

    if len(chunks) == 1 and max_c > 2000:
        warnings.append("Toàn bộ doc trong 1 chunk — nên chunk cho file dài")

    # Score: penalize warnings and extreme sizes
    score = 1.0
    score -= min(0.5, len(warnings) * 0.08)
    if avg_c < 150:
        score -= 0.15
    if avg_c > settings.chunk_size:
        score -= 0.1
    score = max(0.0, min(1.0, score))

    return ChunkAnalysis(
        chunk_count=len(chunks),
        min_chars=min_c,
        max_chars=max_c,
        avg_chars=round(avg_c, 1),
        min_tokens=min(tokens),
        max_tokens=max(tokens),
        avg_tokens=round(sum(tokens) / len(tokens), 1),
        overlap_chars=overlap,
        warnings=warnings,
        quality_score=round(score, 2),
    )
