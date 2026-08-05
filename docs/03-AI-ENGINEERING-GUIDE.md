# AI Engineering Guide — Foundational Knowledge

This document consolidates the knowledge required for teams building an Enterprise Multi-Agent system.

---

## 1. Agentic AI — Core Concepts

### Agent vs Chatbot

| | Traditional Chatbot | Agentic AI |
|---|---|---|
| Input → Output | 1 turn, text only | Multi-step, tool use, planning |
| Knowledge | Training data only | Tools + RAG + real-time data |
| Autonomy | None | Yes (within limits) |
| Error handling | Incorrect answer | Retry, fallback, ask human |

### Agent Loop

```
Observe → Think → Act → Observe → ... → Respond
   ↑                    ↓
   └── Tool result ─────┘
```

**ReAct Pattern** (Reasoning + Acting):
```
Thought: User wants to find contract ABC. I need to query the database.
Action: execute_query("SELECT * FROM contracts WHERE name LIKE '%ABC%'")
Observation: [{id: 1, name: "ABC Corp", ...}]
Thought: Found 1 contract. I will summarize it for the user.
Action: respond("Found contract ABC Corp, signed on...")
```

### When to Use Agent vs Workflow

| Use Agent | Use Workflow (deterministic) |
|------------|-------------------------------|
| Unpredictable input | Fixed structured input |
| Reasoning required | Data transformation only |
| Multi-tool orchestration | 1–2 simple steps |
| Exploratory tasks | Compliance-critical (needs precise audit trail) |

**Best practice:** Hybrid — workflow for deterministic parts, agent for parts requiring reasoning.

---

## 2. Tools & MCP

### Model Context Protocol (MCP)

MCP is an **open standard** (Anthropic) for LLMs to call external tools. Similar to LSP for IDEs.

**Architecture:**
```
┌──────────┐    stdio/SSE/HTTP    ┌─────────────┐
│  Agent   │ ◄──────────────────► │ MCP Server  │
│ (Client) │                      │ (sql, api…) │
└──────────┘                      └──────┬──────┘
                                         │
                                    ┌────▼────┐
                                    │ Backend │
                                    └─────────┘
```

**3 MCP primitives:**
1. **Tools** — Functions the agent can call (`execute_query`, `search`)
2. **Resources** — Data the agent can read (schema, docs)
3. **Prompts** — Reusable prompt templates

### Good Tool Design

```python
# ❌ BAD — tool too broad, unsafe
@tool
def run_sql(query: str) -> str:
    return db.execute(query)  # SQL injection risk!

# ✅ GOOD — narrow, safe tool with validation
@tool
def search_contracts(
    name: str,
    status: Literal["active", "expired", "all"] = "all",
    limit: int = 10
) -> list[Contract]:
    """Search contracts by name. Returns only contracts the user is authorized to view."""
    return contract_repo.search(name=name, status=status, limit=min(limit, 50))
```

**Tool design principles:**
1. **Narrow scope** — 1 tool = 1 clear task
2. **Typed inputs** — Use Pydantic schema, enum, validation
3. **Safe defaults** — Read-only, row limits, timeouts
4. **Descriptive** — Docstring = description for the LLM to read
5. **Idempotent** — Multiple calls cause no side effects (for reads)

---

## 3. Multi-Agent Patterns

### Pattern 1: Supervisor (used in this project)

```
User → Supervisor → [Worker A, Worker B, Worker C] → Supervisor → User
```

The supervisor decides which agent does what. Workers are specialized.

**Pros:** Clear, easy to debug, easy to scale each agent individually.
**Cons:** Supervisor can become a bottleneck.

### Pattern 2: Swarm / Handoff

```
User → Agent A → (handoff) → Agent B → (handoff) → Agent C → User
```

Agents decide on their own when to hand off to another agent.

**Pros:** Flexible, emergent behavior.
**Cons:** Hard to predict, hard to debug.

### Pattern 3: Pipeline

```
User → Agent A → Agent B → Agent C → User
```

Each agent processes sequentially; output becomes input for the next agent.

**Pros:** Deterministic flow.
**Cons:** No parallelism, rigid.

### Pattern 4: Debate / Consensus

```
User → [Agent A, Agent B] debate → Judge Agent → User
```

Multiple agents debate; a judge synthesizes the result.

**Pros:** High quality for complex decisions.
**Cons:** Slow, token-heavy.

**→ This project uses Supervisor + A2A** because it fits enterprise needs (predictable, auditable, scalable).

---

## 4. A2A (Agent-to-Agent)

### Concept

A2A lets agent A call agent B as a **remote tool**, over HTTP + Agent Card.

**Agent Card** (similar to an OpenAPI spec for agents):
```json
{
  "name": "db-agent",
  "description": "Query the database on behalf of the user",
  "url": "https://.../protocols/a2a",
  "skills": [{
    "id": "query-database",
    "name": "Query Database",
    "description": "Execute read-only SQL queries",
    "inputModes": ["text"],
    "outputModes": ["text"]
  }]
}
```

### A2A vs MCP

| | MCP | A2A |
|---|---|---|
| Calls what | Tools (functions) | Agents (autonomous) |
| Complexity | Simple function call | Full agent conversation |
| Use case | DB query, API call | Delegate complex sub-task |
| Protocol | MCP spec | A2A spec (Google) |

**In this project:** The orchestrator uses A2A to call workers; workers use MCP to call tools.

---

## 5. RAG (Retrieval-Augmented Generation)

### Pipeline

```
Documents → Chunk → Embed → Store in Vector DB
                                    ↓
User query → Embed → Retrieve top-k → Augment prompt → LLM → Answer
```

### Best practices

| Aspect | Recommendation |
|--------|---------------|
| Chunk size | 512–1024 tokens, overlap 10–20% |
| Embedding model | text-embedding-3-large or domain-specific |
| Retrieval | Hybrid (semantic + keyword/BM25) |
| Reranking | Cross-encoder reranker for top-k |
| Grounding | Always cite source in the response |

### RAG vs Fine-tuning

| | RAG | Fine-tuning |
|---|---|---|
| Update knowledge | Instant (re-index) | Requires retrain |
| Cost | Retrieval latency | Training cost |
| Accuracy | Depends on retrieval quality | Learns deeper patterns |
| Use case | FAQ, docs, knowledge base | Style, format, reasoning |

**→ Use both:** RAG for knowledge, FT for behavior.

---

## 6. Prompt Engineering for Agents

### System Prompt structure

```markdown
# Role
You are a DB Agent specialized in querying the database for the multi-agent system.

# Capabilities
- execute_query: Run SELECT queries (read-only)
- list_tables: List tables
- describe_table: View schema

# Rules
1. NEVER run INSERT/UPDATE/DELETE
2. Always use parameterized queries
3. Limit to 100 rows per query
4. If unsure about schema, call describe_table first

# Output format
- Respond in Vietnamese
- Include the SQL executed (in a code block)
- If nothing is found, state clearly and suggest an alternative query
```

### Anti-patterns

| ❌ Avoid | ✅ Use instead |
|----------|-------------|
| "Be helpful" (vague) | Specific rules and examples |
| Too long (>2000 tokens) | Split into Skills |
| Hard-code data in the prompt | Use RAG or tools |
| No output format | Define format clearly |

---

## 7. Evaluation (Eval)

### Why eval matters

LLM outputs are **non-deterministic** — they cannot be unit-tested like regular code. Eval is the only way to ensure quality.

### Types of eval

| Type | Description | When |
|------|--------|---------|
| **Unit eval** | 1 input → 1 expected output | Every PR |
| **Batch eval** | N test cases → pass rate | Before deploy |
| **Continuous eval** | Production samples → monitor | Ongoing |
| **A/B eval** | Model A vs B | Model comparison |

### Designing eval cases

```yaml
# eval/cases/db-agent-basic.yaml
- id: count-contracts
  input: "How many active contracts are there?"
  expected_tools: ["execute_query"]
  expected_sql_contains: ["SELECT", "COUNT", "contracts", "active"]
  grading:
  - type: tool_call_accuracy
    weight: 0.4
  - type: llm_judge
    criteria: "Response mentions a number and explains it's active contracts"
    weight: 0.6
```

### Graders

| Grader | Used for |
|--------|----------|
| Exact match | Structured output |
| Contains / Regex | SQL queries, formats |
| LLM-as-judge | Open-ended quality |
| Tool call accuracy | Agent tool selection |
| Custom Python | Domain-specific logic |

---

## 8. Fine-tuning

### When to fine-tune

| Signal | Action |
|--------|--------|
| Agent answers correctly but wrong format | SFT |
| Agent selects wrong tool | RFT with tool-call grader |
| 2 responses both correct, 1 better | DPO |
| Missing domain knowledge | RAG first, SFT if RAG is insufficient |

### Pipeline

```
1. Collect traces (production + synthetic)
2. Filter high-quality examples
3. Format as training pairs
4. Train (SFT/DPO/RFT)
5. Evaluate on held-out set
6. A/B deploy if improvement > threshold
7. Monitor for regression
```

### Data quality > quantity

- 100 high-quality examples > 10,000 noisy examples
- Always have human review before training
- Track lineage: trace_id → training example → model version

---

## 9. Security for Agentic Systems

### Threat model

| Threat | Mitigation |
|--------|------------|
| Prompt injection | Input sanitization, tool allowlist |
| Data exfiltration | Row-level security, output filtering |
| Privilege escalation | Least privilege per agent |
| Tool abuse | Rate limits, input validation |
| Hallucination | Grounding, eval, confidence thresholds |

### Defense in depth

```
Layer 1: Input guardrails (content filter, PII detection)
Layer 2: Agent instructions (refuse harmful requests)
Layer 3: Tool permissions (read-only, allowlist)
Layer 4: Output guardrails (PII redaction, fact-check)
Layer 5: Human approval (destructive actions)
```

---

## 10. Observability

### 3 pillars for AI systems

| Pillar | Metrics | Tools |
|--------|---------|-------|
| **Traces** | Latency per step, tool call chain | OpenTelemetry |
| **Logs** | Prompt, response, errors | Structured JSON |
| **Metrics** | Token usage, error rate, eval score | Prometheus |

### Debug workflow

```
User reports bad response
  → Find trace_id in App Insights
  → Replay: input → tool calls → intermediate steps → output
  → Identify: wrong tool? bad retrieval? prompt issue?
  → Fix: skill update / eval case / fine-tune
  → Verify: re-run eval suite
```

---

## 11. References

### Official
- [MCP Specification](https://modelcontextprotocol.io)
- [A2A Protocol](https://google.github.io/A2A/)
- [Azure AI Foundry Agents](https://learn.microsoft.com/azure/foundry/agents/)
- [LangGraph Multi-Agent](https://langchain-ai.github.io/langgraph/)

### Books & Courses
- "Building LLM Apps" — patterns and production lessons
- "AI Engineering" (Chip Huyen) — MLOps for LLMs
- Microsoft Learn: AI-102, AI-050

### Community
- LangChain Discord, Azure AI Foundry GitHub Discussions
- MCP GitHub: modelcontextprotocol/servers (reference implementations)
