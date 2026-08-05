> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# Azure Blob Indexer — Tự động index tài liệu lên Azure Search

> P1 còn lại: **không chạy trong code local** — setup trên Azure Portal. Sau khi xong, agent query qua `hybrid_search()` → `azure_search()` như bình thường.

---

## Khi nào dùng?

| Scenario | Dùng gì |
|----------|---------|
| Dev local, vài chục doc | pgvector + `scripts/ingest_file.py` |
| Production, hàng nghìn PDF/wiki | Azure Blob + Indexer → Azure Search |
| Hybrid | Cả hai — Azure primary, pgvector fallback |

---

## Setup trên Azure (tóm tắt)

### 1. Tạo Storage Account + Container

```
Azure Portal → Storage Account → Containers → tạo "documents"
Upload PDF/DOCX vào container
```

### 2. Tạo Azure AI Search index

Index `knowledge-index` với fields (khớp code):

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Edm.String | key |
| `doc_id` | Edm.String | filterable |
| `title` | Edm.String | searchable |
| `content` | Edm.String | searchable |
| `domain` | Edm.String | filterable, facetable |
| `source` | Edm.String | filterable |

### 3. Tạo Data Source

```
Azure AI Search → Data sources → Add
Type: Azure Blob Storage
Connection string: từ Storage Account
Container: documents
```

### 4. Tạo Skillset (optional — chunking trên Azure)

Nếu file PDF lớn, dùng **Text Split skill**:
- `maximumPageLength`: 800 (khớp `CHUNK_SIZE`)
- `pageOverlapLength`: 120 (khớp `CHUNK_OVERLAP`)

Skillset pipeline:
```
Document Extraction → Text Split → Merge → Index projection
```

### 5. Tạo Indexer

```
Azure AI Search → Indexers → Add
Data source: blob-documents
Target index: knowledge-index
Skillset: (nếu có)
Schedule: hourly hoặc on-demand
```

### 6. Chạy indexer + verify

```
Indexers → Run → kiểm tra Execution history
Search explorer: query "hop dong"
```

### 7. Điền `.env` trên app server

```env
AZURE_SEARCH_ENDPOINT=https://YOUR.search.windows.net
AZURE_SEARCH_API_KEY=...
AZURE_SEARCH_INDEX_NAME=knowledge-index
```

---

## Đồng bộ với pgvector?

Hiện tại **không tự sync**. Hai lựa chọn:

| Cách | Mô tả |
|------|-------|
| Azure-only | Chỉ index lên Azure, pgvector làm fallback dev |
| Dual-write | Sau ingest local, chạy `python scripts/index_azure.py` |
| Azure-primary | Production chỉ dùng Blob indexer, bỏ pgvector ingest |

---

## So sánh chunking: local vs Azure

| | Local (`chunk_text`) | Azure (Text Split skill) |
|--|---------------------|--------------------------|
| Preview | `--preview`, `/chunk-eval` | Search explorer sau index |
| Tune | `CHUNK_SIZE`, `CHUNK_OVERLAP` | Skill parameters |
| Eval query | `POST /chunk-eval` | Manual query trên Portal |

Khuyến nghị: tune chunking local trước với `chunk-eval`, rồi copy params sang Azure skillset.
