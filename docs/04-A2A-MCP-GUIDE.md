# A2A & MCP — Implementation Guide

## 1. MCP Server Development

### MCP server structure

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

| Mode | Use when | Protocol |
|------|----------|----------|
| **stdio** | Local dev, Cursor IDE | stdin/stdout |
| **SSE** | Remote, single client | HTTP Server-Sent Events |
| **Streamable HTTP** | Production, scalable | HTTP POST + SSE |

### Connecting MCP to a Foundry Agent

```bash
# 1. Deploy MCP server (container or Azure Functions)
# 2. Create connection
azd ai connection create \
  --kind remote-tool \
  --target https://your-mcp-server.example.com/mcp \
  --auth-type managed-identity

# 3. Add to toolbox
azd ai toolbox add \
  --tool mcp \
  --connection <connection-id> \
  --name sql-tools
```

### Connecting MCP to Cursor IDE (dev)

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

### Step 1: Enable A2A on the target agent

For a Foundry hosted agent, the A2A endpoint is automatically available at:
```
https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/a2a
```

Verify:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$A2A_ENDPOINT/agentCard/v1.0"
```

### Step 2: Create a RemoteA2A connection

```bash
azd ai connection create \
  --kind remote-a2a \
  --target $TARGET_AGENT_A2A_ENDPOINT \
  --auth-type aad \
  --name db-agent-a2a
```

### Step 3: Attach A2A tools to the orchestrator

In `azure.yaml` or toolbox config:
```yaml
tools:
  - type: a2a_preview
    name: db-agent
    connection: db-agent-a2a
    description: "Query the database. Use when the user asks about data, metrics, or records."
  - type: a2a_preview
    name: research-agent
    connection: research-agent-a2a
    description: "Search documents, contracts, and regulations. Use when information lookup is needed."
```

### Step 4: Orchestrator system prompt

```markdown
You are the Orchestrator Agent. You do NOT query the database or search on your own.
You coordinate specialized agents:

- **db-agent**: Call when data from the database is needed (metrics, lists, statistics)
- **research-agent**: Call when documents, regulations, or concept explanations are needed

Rules:
1. Analyze the request → determine which agent(s) to call
2. You may call multiple agents in parallel if tasks are independent
3. Synthesize results from agents into the final response for the user
4. If unsure, ask the user instead of guessing
```

---

## 3. Self-hosted A2A (outside Foundry)

If you need an agent running self-hosted with A2A:

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

### Test MCP server independently

```bash
# Use MCP Inspector
npx @modelcontextprotocol/inspector python mcp-servers/sql-server/server.py

# Or curl (SSE mode)
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
      "parts": [{"type": "text", "text": "How many active contracts are there?"}]
    }
  }'
```

### Integration test

```python
# tests/test_orchestrator_a2a.py
async def test_orchestrator_calls_db_agent():
    response = await orchestrator.invoke(
        "How many customers are in the system?"
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
