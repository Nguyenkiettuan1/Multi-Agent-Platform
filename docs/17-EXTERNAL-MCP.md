# External MCP integration

How to add MCP servers for **Cursor IDE** (development) vs **chat runtime** (end users).

## Two channels

| Channel | Used by | Config file |
|---------|---------|-------------|
| `.cursor/mcp.json` | You in Cursor IDE | Plug & play for coding |
| **App runtime** | Chat UI `/api/v1/chat` | `config/mcp_servers.yaml` + `ToolHub` |

Catalog template: `config/mcp_servers.yaml`.

---

## 1. MCP for Cursor (development)

### Step 1 — Copy example config

```powershell
copy .cursor\mcp.json.example .cursor\mcp.json
```

Adjust `filesystem` paths for your machine (e.g. `./multi-agent`).

### Step 2 — Enable in Cursor

**Cursor Settings → MCP** → Reload or restart Cursor.

Example servers in the template:

| MCP | Purpose |
|-----|---------|
| `sql-server` | Dev DB queries |
| `search-server` | Test RAG + web |
| `filesystem` | Read/edit project files |
| `fetch` | Fetch URL content |

### Step 3 — Optional OCR (PaddleOCR MCP)

```powershell
pip install paddleocr_mcp
# paddlepaddle required for local OCR — see PaddleOCR docs
```

Add to `.cursor/mcp.json`:

```json
"paddleocr": {
  "command": "python",
  "args": ["-m", "paddleocr_mcp", "--ppocr_source", "local"]
}
```

**Note:** Chat app OCR uses `builtin-ocr` (Tesseract → Azure vision) by default; see `config/media_tasks.yaml`.

### Other community MCPs

```json
"brave-search": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env": { "BRAVE_API_KEY": "your-key" }
}
```

Reference: [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers).

### Verify MCP

```bash
npx @modelcontextprotocol/inspector python mcp-servers/sql-server/server.py
```

---

## 2. MCP for chat runtime (production path)

`ToolHub` (`core/mcp/hub.py`) loads `config/mcp_servers.yaml` and merges **internal** Python tools with **external** stdio MCP processes.

### Enable a server

1. Open `config/mcp_servers.yaml`
2. Set `enabled: true` for the server (`fetch`, `paddleocr`, …)
3. Ensure the server is listed in `agents/registry.yaml` under `action-worker.tools`
4. Restart: `python -m gateway.main`
5. Verify: `GET /api/v1/mcp/catalog`

### Built-in app tools

| Server | Purpose |
|--------|---------|
| `builtin-translate` | Text translation (LLM) |
| `builtin-ocr` | Image OCR (Tesseract → vision LLM) |
| `builtin-image` | Merge images (Pillow) |
| `sql-server` | Read-only SQL |
| `search-server` | RAG + web search |

### Chat examples

- *"Translate to English: Contract effective from 1/1/2026"*
- Upload invoice image → OCR extracts text automatically
- *"Merge these two images horizontally"* (with attachments)

### OCR flow (upload)

```
Frontend upload → gateway materialize_attachments()
  → triage (ACTION) → planner binds builtin-ocr/ocr_extract + file_path
  → action_worker → hub.call_tool → internal_tools._ocr_extract
```

Config: `config/media_tasks.yaml`, classifier: `core/planning/llm_media_classifier.py`.

### Extension pattern

```
mcp-servers/<name>/server.py     # stdio MCP for Cursor + optional app
core/mcp/<name>_tools.py         # shared logic
config/mcp_servers.yaml          # enabled, runtime: app|both|cursor
agents/registry.yaml             # agent tool allowlist
workflows/workers/action_worker.py
```

---

## 3. Security

- Store API keys in `.env` or local `mcp.json` (gitignored)
- Do not commit tokens in `mcp.json.example`
- Filesystem/OCR MCP can read local files — enable only trusted servers

---

## Summary

| Goal | Action |
|------|--------|
| OCR / fetch / GitHub while **coding** | Edit `.cursor/mcp.json` |
| OCR / translate in **chat UI** | Enable servers in `mcp_servers.yaml` |
| Knowledge PDF ingest OCR | Extend `core/search/ingestion.py` |
| List active tools | `GET /api/v1/mcp/catalog` |
