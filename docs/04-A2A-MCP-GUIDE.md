> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# A2A & MCP — Hướng dẫn triển khai

## 1. MCP Server Development

### Cấu trúc MCP server

```
mcp-servers/sql-server/
├── server.py          # Entry point
├── tools/
│   ├── list_tables.py
│   ├── describe_table.py
│   └── execute_query.py
├── config.py          # Connection, limits
├── requirements.txt
└── README.md
```

### Transport modes

| Mode | Dùng khi | Protocol |
|------|----------|----------|
| **stdio** | Local dev, Cursor IDE | stdin/stdout |
| **SSE** | Remote, single client | HTTP Server-Sent Events |
| **Streamable HTTP** | Production, scalable | HTTP POST + SSE |

### Kết nối MCP với Foundry Agent

```bash
# 1. Deploy MCP server (container hoặc Azure Functions)
# 2. Tạo connection
azd ai connection create \
  --kind remote-tool \
  --target https://your-mcp-server.example.com/mcp \
  --auth-type managed-identity

# 3. Thêm vào toolbox
azd ai toolbox add \
  --tool mcp \
  --connection <connection-id> \
  --name sql-tools
```

### Kết nối MCP với Cursor IDE (dev)

File `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "sql-server": {
      "command": "python",
      "args": ["mcp-servers/sql-server/server.py"],
      "env": {
        "DATABASE_URL": "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/multiagent?options=-csearch_path%3Dapp"
      }
    }
  }
}
```

---

## 2. A2A Setup

### Bước 1: Enable A2A trên target agent

Với Foundry hosted agent, A2A endpoint tự động available tại:
```
https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/a2a
```

Verify:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$A2A_ENDPOINT/agentCard/v1.0"
```

### Bước 2: Tạo RemoteA2A connection

```bash
azd ai connection create \
  --kind remote-a2a \
  --target $TARGET_AGENT_A2A_ENDPOINT \
  --auth-type aad \
  --name db-agent-a2a
```

### Bước 3: Gắn A2A tool vào orchestrator

Trong `azure.yaml` hoặc toolbox config:
```yaml
tools:
  - type: a2a_preview
    name: db-agent
    connection: db-agent-a2a
    description: "Truy vấn database. Dùng khi user hỏi về dữ liệu, số liệu, bản ghi."
  - type: a2a_preview
    name: research-agent
    connection: research-agent-a2a
    description: "Tìm kiếm tài liệu, hợp đồng, quy định. Dùng khi cần tra cứu thông tin."
```

### Bước 4: Orchestrator system prompt

```markdown
Bạn là Orchestrator Agent. Bạn KHÔNG tự query database hay search.
Bạn điều phối các agent chuyên biệt:

- **db-agent**: Gọi khi cần dữ liệu từ database (số liệu, danh sách, thống kê)
- **research-agent**: Gọi khi cần tìm tài liệu, tra cứu quy định, giải thích khái niệm

Quy tắc:
1. Phân tích request → xác định agent(s) cần gọi
2. Có thể gọi nhiều agent song song nếu tasks độc lập
3. Tổng hợp kết quả từ agents thành response cuối cho user
4. Nếu không chắc, hỏi lại user thay vì đoán
```

---

## 3. Self-hosted A2A (ngoài Foundry)

Nếu cần agent chạy self-hosted với A2A:

```python
# agents/db-agent/a2a_server.py
from a2a.server import A2AServer
from a2a.types import AgentCard, AgentSkill

card = AgentCard(
    name="db-agent",
    description="Database query agent",
    url="http://localhost:8001/a2a",
    skills=[
        AgentSkill(
            id="query-database",
            name="Query Database",
            description="Execute read-only SQL queries",
        )
    ],
)

server = A2AServer(agent_card=card, handler=handle_request)
```

---

## 4. Testing MCP & A2A

### Test MCP server độc lập

```bash
# Dùng MCP Inspector
npx @modelcontextprotocol/inspector python mcp-servers/sql-server/server.py

# Hoặc curl (SSE mode)
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Test A2A endpoint

```bash
# Get agent card
curl $A2A_ENDPOINT/agentCard/v1.0

# Send task
curl -X POST $A2A_ENDPOINT/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Có bao nhiêu hợp đồng active?"}]
    }
  }'
```

### Integration test

```python
# tests/test_orchestrator_a2a.py
async def test_orchestrator_calls_db_agent():
    response = await orchestrator.invoke(
        "Có bao nhiêu khách hàng trong hệ thống?"
    )
    assert "db-agent" in response.tool_calls
    assert response.final_answer contains a number
```

---

## 5. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| MCP tools/list returns 0 | Connection auth failed | Check credentials, RBAC |
| A2A 404 on agent card | A2A not enabled | Enable incoming A2A on target |
| Agent calls wrong tool | Ambiguous tool descriptions | Improve descriptions, add examples |
| Slow response | Sequential tool calls | Enable parallel A2A dispatch |
| Token overflow | Too much context | Summarize intermediate results |
