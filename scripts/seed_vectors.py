#!/usr/bin/env python3
"""Seed knowledge_documents for RAG — python scripts/seed_vectors.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from config import get_settings
from core.search.embeddings import embed_text
from core.search.pgvector_store import upsert_document

SAMPLE_DOCS = [
    {
        "doc_id": "legal-contract-basics",
        "title": "Cơ bản về hợp đồng dân sự",
        "content": (
            "Hợp đồng là sự thỏa thuận giữa các bên về việc xác lập, thay đổi "
            "hoặc chấm dứt quyền và nghĩa vụ dân sự. Điều khoản thanh toán phải "
            "ghi rõ thời hạn, phương thức và đồng tiền thanh toán."
        ),
        "domain": "legal",
    },
    {
        "doc_id": "legal-labor-law",
        "title": "Hợp đồng lao động",
        "content": (
            "Hợp đồng lao động phải được ký bằng văn bản. Thời hạn thử việc "
            "không quá 60 ngày với công việc cần trình độ cao."
        ),
        "domain": "legal",
    },
    {
        "doc_id": "general-rest-api",
        "title": "REST API Overview",
        "content": (
            "REST (Representational State Transfer) là kiến trúc API sử dụng HTTP "
            "methods: GET, POST, PUT, DELETE. Stateless — mỗi request độc lập."
        ),
        "domain": "general",
    },
    {
        "doc_id": "internal-contract-policy",
        "title": "Quy trình quản lý hợp đồng nội bộ",
        "content": (
            "Mọi hợp đồng trên 500 triệu VND cần phê duyệt cấp Giám đốc. "
            "Hợp đồng active được theo dõi trong hệ thống contracts."
        ),
        "domain": "general",
    },
]


async def seed_vectors() -> None:
    settings = get_settings()
    engine = create_engine(settings.migrate_database_url or settings.database_url)

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT COUNT(*) FROM app.knowledge_documents")
        ).scalar()
        if exists and exists > 0:
            print(f"Knowledge base already seeded ({exists} docs).")
            return

    for doc in SAMPLE_DOCS:
        embedding = await embed_text(f"{doc['title']}\n{doc['content']}")
        upsert_document(
            doc_id=doc["doc_id"],
            title=doc["title"],
            content=doc["content"],
            domain=doc["domain"],
            source="seed",
            embedding=embedding,
        )
        print(f"  + {doc['doc_id']}" + (" (with embedding)" if embedding else " (FTS only)"))

    print(f"Seeded {len(SAMPLE_DOCS)} knowledge documents.")


if __name__ == "__main__":
    asyncio.run(seed_vectors())
