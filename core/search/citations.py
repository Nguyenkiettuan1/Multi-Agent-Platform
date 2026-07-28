"""Structured citations for knowledge + web search."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class SourceCitation:
    ref_id: str
    title: str
    excerpt: str
    source_type: str  # knowledge | web
    backend: str
    url: str | None = None
    doc_id: str | None = None
    score: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def citations_from_knowledge_hits(hits, *, prefix: str = "D") -> list[SourceCitation]:
    from core.search.pgvector_store import SearchHit

    citations: list[SourceCitation] = []
    for i, h in enumerate(hits, 1):
        if not isinstance(h, SearchHit):
            continue
        citations.append(
            SourceCitation(
                ref_id=f"{prefix}{i}",
                title=h.title,
                excerpt=h.content[:500],
                source_type="knowledge",
                backend=h.backend,
                doc_id=h.doc_id,
                score=h.score,
            )
        )
    return citations


def citations_from_web_results(results: list[dict]) -> list[SourceCitation]:
    citations: list[SourceCitation] = []
    for i, r in enumerate(results, 1):
        citations.append(
            SourceCitation(
                ref_id=f"W{i}",
                title=r.get("title", "Web result"),
                excerpt=(r.get("content") or r.get("snippet") or "")[:2000],
                source_type="web",
                backend="web_search",
                url=r.get("url"),
                score=r.get("score"),
            )
        )
    return citations


def format_context_for_llm(citations: list[SourceCitation]) -> str:
    if not citations:
        return "Không tìm thấy tài liệu liên quan."
    parts = []
    for c in citations:
        header = f"[{c.ref_id}] {c.title}"
        if c.url:
            header += f" — {c.url}"
        elif c.doc_id:
            header += f" (doc_id={c.doc_id}, backend={c.backend})"
        parts.append(f"{header}\n{c.excerpt[:2500]}")
    return "\n\n".join(parts)


def format_references_block(citations: list[SourceCitation]) -> str:
    if not citations:
        return ""
    lines = ["## Nguồn tham khảo"]
    for c in citations:
        if c.url:
            lines.append(f"- **[{c.ref_id}]** {c.title} — {c.url}")
        elif c.doc_id:
            lines.append(f"- **[{c.ref_id}]** {c.title} (`{c.doc_id}`, {c.backend})")
        else:
            lines.append(f"- **[{c.ref_id}]** {c.title}")
    return "\n".join(lines)


CITATION_INSTRUCTION = """
BẮT BUỘC khi trả lời:
- Đọc kỹ nội dung từng nguồn [D1], [W2]... rồi TỔNG HỢP thành câu trả lời mạch lạc (tiếng Việt).
- Mỗi fact quan trọng gắn mã nguồn inline: [W1], [D2] — KHÔNG copy nguyên block tiêu đề/URL/snippet.
- KHÔNG viết "Đã tìm thấy X nguồn" hay liệt kê lại danh sách nguồn.
- KHÔNG thêm mục "## Nguồn tham khảo" (UI hiển thị riêng).
- Không bịa. Thiếu thông tin → nói rõ.
""".strip()


def merge_worker_citations(worker_results) -> list[SourceCitation]:
    seen: set[str] = set()
    merged: list[SourceCitation] = []
    for result in worker_results:
        for raw in getattr(result, "citations", None) or []:
            if isinstance(raw, SourceCitation):
                c = raw
            else:
                c = SourceCitation(**raw)
            key = c.url or c.doc_id or c.ref_id
            if key in seen:
                continue
            seen.add(key)
            merged.append(c)
    return merged


def strip_references_block(text: str) -> str:
    """Remove trailing references section from response body (UI uses structured citations)."""
    marker = "## Nguồn tham khảo"
    if marker in text:
        return text.split(marker, 1)[0].rstrip()
    return text


def append_citations_to_response(response: str, worker_results) -> tuple[str, list[dict]]:
    citations = merge_worker_citations(worker_results)
    cleaned = strip_references_block(response)
    if not citations:
        return cleaned, []
    return cleaned, [c.to_dict() for c in citations]
