# Azure Blob Indexer — Automatically Index Documents to Azure Search

> Remaining P1: **does not run in local code** — set up on Azure Portal. Once done, the agent queries via `hybrid_search()` → `azure_search()` as usual.

---

## When to use?

| Scenario | Use |
|----------|-----|
| Local dev, dozens of docs | pgvector + `scripts/ingest_file.py` |
| Production, thousands of PDFs/wiki | Azure Blob + Indexer → Azure Search |
| Hybrid | Both — Azure primary, pgvector fallback |

---

## Azure setup (summary)

### 1. Create Storage Account + Container

```
Azure Portal → Storage Account → Containers → create "documents"
Upload PDF/DOCX to container
```

### 2. Create Azure AI Search index

Index `knowledge-index` with fields (matching code):

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Edm.String | key |
| `doc_id` | Edm.String | filterable |
| `title` | Edm.String | searchable |
| `content` | Edm.String | searchable |
| `domain` | Edm.String | filterable, facetable |
| `source` | Edm.String | filterable |

### 3. Create Data Source

```
Azure AI Search → Data sources → Add
Type: Azure Blob Storage
Connection string: from Storage Account
Container: documents
```

### 4. Create Skillset (optional — chunking on Azure)

For large PDF files, use **Text Split skill**:
- `maximumPageLength`: 800 (matches `CHUNK_SIZE`)
- `pageOverlapLength`: 120 (matches `CHUNK_OVERLAP`)

Skillset pipeline:
```
Document Extraction → Text Split → Merge → Index projection
```

### 5. Create Indexer

```
Azure AI Search → Indexers → Add
Data source: blob-documents
Target index: knowledge-index
Skillset: (if applicable)
Schedule: hourly or on-demand
```

### 6. Run indexer + verify

```
Indexers → Run → check Execution history
Search explorer: query "hop dong"
```

### 7. Fill in `.env` on app server

```env
AZURE_SEARCH_ENDPOINT=https://YOUR.search.windows.net
AZURE_SEARCH_API_KEY=...
AZURE_SEARCH_INDEX_NAME=knowledge-index
```

---

## Sync with pgvector?

Currently **no auto-sync**. Two options:

| Approach | Description |
|----------|-------------|
| Azure-only | Index only to Azure, pgvector as dev fallback |
| Dual-write | After local ingest, run `python scripts/index_azure.py` |
| Azure-primary | Production uses Blob indexer only, skip pgvector ingest |

---

## Chunking comparison: local vs Azure

| | Local (`chunk_text`) | Azure (Text Split skill) |
|--|---------------------|--------------------------|
| Preview | `--preview`, `/chunk-eval` | Search explorer after index |
| Tune | `CHUNK_SIZE`, `CHUNK_OVERLAP` | Skill parameters |
| Eval query | `POST /chunk-eval` | Manual query on Portal |

Recommendation: tune chunking locally with `chunk-eval` first, then copy params to Azure skillset.
