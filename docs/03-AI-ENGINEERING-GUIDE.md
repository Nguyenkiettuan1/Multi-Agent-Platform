> **English guides:** [README](../README.md) · [Local setup](12-LOCAL-SETUP.md) · [Docs index](README.md)  
> This document may still contain Vietnamese in places; prefer the English guides above for running the project.

# AI Engineering Guide — Kiến thức nền tảng

Tài liệu này tổng hợp kiến thức cần thiết cho team xây dựng hệ thống Multi-Agent Enterprise.

---

## 1. Agentic AI — Khái niệm cốt lõi

### Agent vs Chatbot

| | Chatbot truyền thống | Agentic AI |
|---|---|---|
| Input → Output | 1 turn, text only | Multi-step, tool use, planning |
| Knowledge | Chỉ training data | Tools + RAG + real-time data |
| Autonomy | Không | Có (trong giới hạn) |
| Error handling | Trả lời sai | Retry, fallback, ask human |

### Vòng lặp Agent (Agent Loop)

```
Observe → Think → Act → Observe → ... → Respond
   ↑                    ↓
   └── Tool result ─────┘
```

**ReAct Pattern** (Reasoning + Acting):
```
Thought: User muốn tìm hợp đồng ABC. Tôi cần query database.
Action: execute_query("SELECT * FROM contracts WHERE name LIKE '%ABC%'")
Observation: [{id: 1, name: "ABC Corp", ...}]
Thought: Tìm thấy 1 hợp đồng. Tôi sẽ tóm tắt cho user.
Action: respond("Tìm thấy hợp đồng ABC Corp, ký ngày...")
```

### Khi nào dùng Agent vs Workflow

| Dùng Agent | Dùng Workflow (deterministic) |
|------------|-------------------------------|
| Input không predictable | Input có cấu trúc cố định |
| Cần reasoning | Chỉ cần transform data |
| Multi-tool orchestration | 1-2 bước đơn giản |
| Exploratory tasks | Compliance-critical (cần audit trail chính xác) |

**Best practice:** Hybrid — workflow cho phần deterministic, agent cho phần cần reasoning.

---

## 2. Tools & MCP

### Model Context Protocol (MCP)

MCP là **chuẩn mở** (Anthropic) để LLM gọi external tools. Tương tự LSP cho IDE.

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

**3 primitives của MCP:**
1. **Tools** — Functions agent có thể gọi (`execute_query`, `search`)
2. **Resources** — Data agent có thể đọc (schema, docs)
3. **Prompts** — Template prompts tái sử dụng

### Thiết kế Tool tốt

```python
# ❌ BAD — tool quá rộng, không an toàn
@tool
def run_sql(query: str) -> str:
    return db.execute(query)  # SQL injection risk!

# ✅ GOOD — tool hẹp, an toàn, có validation
@tool
def search_contracts(
    name: str,
    status: Literal["active", "expired", "all"] = "all",
    limit: int = 10
) -> list[Contract]:
    """Tìm hợp đồng theo tên. Chỉ trả về contracts user có quyền xem."""
    return contract_repo.search(name=name, status=status, limit=min(limit, 50))
```

**Nguyên tắc thiết kế tool:**
1. **Narrow scope** — 1 tool = 1 việc rõ ràng
2. **Typed inputs** — Dùng Pydantic schema, enum, validation
3. **Safe defaults** — Read-only, row limits, timeouts
4. **Descriptive** — Docstring = mô tả cho LLM đọc
5. **Idempotent** — Gọi nhiều lần không gây side effect (nếu read)

---

## 3. Multi-Agent Patterns

### Pattern 1: Supervisor (dùng trong project này)

```
User → Supervisor → [Worker A, Worker B, Worker C] → Supervisor → User
```

Supervisor quyết định agent nào làm gì. Workers chuyên biệt.

**Ưu:** Rõ ràng, dễ debug, dễ scale từng agent.
**Nhược:** Supervisor có thể bottleneck.

### Pattern 2: Swarm / Handoff

```
User → Agent A → (handoff) → Agent B → (handoff) → Agent C → User
```

Agent tự quyết định chuyển cho agent khác.

**Ưu:** Linh hoạt, emergent behavior.
**Nhược:** Khó predict, khó debug.

### Pattern 3: Pipeline

```
User → Agent A → Agent B → Agent C → User
```

Mỗi agent xử lý tuần tự, output = input của agent tiếp.

**Ưu:** Deterministic flow.
**Nhược:** Không parallel, rigid.

### Pattern 4: Debate / Consensus

```
User → [Agent A, Agent B] debate → Judge Agent → User
```

Nhiều agent debate, judge tổng hợp.

**Ưu:** Quality cao cho complex decisions.
**Nhược:** Chậm, tốn token.

**→ Project này dùng Supervisor + A2A** vì phù hợp enterprise (predictable, auditable, scalable).

---

## 4. A2A (Agent-to-Agent)

### Khái niệm

A2A cho phép agent A gọi agent B như một **remote tool**, qua HTTP + Agent Card.

**Agent Card** (tương tự OpenAPI spec cho agent):
```json
{
  "name": "db-agent",
  "description": "Truy vấn database thay người dùng",
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
| Gọi gì | Tools (functions) | Agents (autonomous) |
| Complexity | Simple function call | Full agent conversation |
| Use case | DB query, API call | Delegate complex sub-task |
| Protocol | MCP spec | A2A spec (Google) |

**Trong project:** Orchestrator dùng A2A gọi workers; Workers dùng MCP gọi tools.

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
| Embedding model | text-embedding-3-large hoặc domain-specific |
| Retrieval | Hybrid (semantic + keyword/BM25) |
| Reranking | Cross-encoder reranker cho top-k |
| Grounding | Luôn cite source trong response |

### RAG vs Fine-tuning

| | RAG | Fine-tuning |
|---|---|---|
| Update knowledge | Instant (re-index) | Cần retrain |
| Cost | Retrieval latency | Training cost |
| Accuracy | Phụ thuộc retrieval quality | Học pattern sâu |
| Use case | FAQ, docs, knowledge base | Style, format, reasoning |

**→ Dùng cả hai:** RAG cho knowledge, FT cho behavior.

---

## 6. Prompt Engineering cho Agents

### System Prompt structure

```markdown
# Role
Bạn là DB Agent chuyên truy vấn database cho hệ thống multi-agent.

# Capabilities
- execute_query: Chạy SELECT queries (read-only)
- list_tables: Liệt kê bảng
- describe_table: Xem schema

# Rules
1. KHÔNG BAO GIỜ chạy INSERT/UPDATE/DELETE
2. Luôn dùng parameterized queries
3. Giới hạn 100 rows mỗi query
4. Nếu không chắc schema, gọi describe_table trước

# Output format
- Trả lời bằng tiếng Việt
- Kèm SQL đã chạy (trong code block)
- Nếu không tìm thấy, nói rõ và gợi ý query khác
```

### Anti-patterns

| ❌ Tránh | ✅ Thay bằng |
|----------|-------------|
| "Be helpful" (vague) | Specific rules và examples |
| Quá dài (>2000 tokens) | Tách vào Skills |
| Hard-code data trong prompt | Dùng RAG hoặc tools |
| Không có output format | Định nghĩa rõ format |

---

## 7. Evaluation (Eval)

### Tại sao eval quan trọng

LLM outputs **non-deterministic** — không thể unit test như code thường. Eval là cách duy nhất đảm bảo quality.

### Loại eval

| Type | Mô tả | Khi nào |
|------|--------|---------|
| **Unit eval** | 1 input → 1 expected output | Mỗi PR |
| **Batch eval** | N test cases → pass rate | Trước deploy |
| **Continuous eval** | Production samples → monitor | Ongoing |
| **A/B eval** | Model A vs B | Model comparison |

### Thiết kế eval case

```yaml
# eval/cases/db-agent-basic.yaml
- id: count-contracts
  input: "Có bao nhiêu hợp đồng đang active?"
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

| Grader | Dùng cho |
|--------|----------|
| Exact match | Structured output |
| Contains / Regex | SQL queries, formats |
| LLM-as-judge | Open-ended quality |
| Tool call accuracy | Agent tool selection |
| Custom Python | Domain-specific logic |

---

## 8. Fine-tuning

### Khi nào fine-tune

| Signal | Action |
|--------|--------|
| Agent trả lời đúng nhưng sai format | SFT |
| Agent chọn sai tool | RFT với tool-call grader |
| 2 responses đều đúng, 1 tốt hơn | DPO |
| Thiếu domain knowledge | RAG trước, SFT nếu RAG không đủ |

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
- Luôn có human review trước khi train
- Track lineage: trace_id → training example → model version

---

## 9. Security cho Agentic Systems

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

### 3 pillars cho AI systems

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

## 11. Tài liệu tham khảo

### Official
- [MCP Specification](https://modelcontextprotocol.io)
- [A2A Protocol](https://google.github.io/A2A/)
- [Azure AI Foundry Agents](https://learn.microsoft.com/azure/foundry/agents/)
- [LangGraph Multi-Agent](https://langchain-ai.github.io/langgraph/)

### Books & Courses
- "Building LLM Apps" — patterns và production lessons
- "AI Engineering" (Chip Huyen) — MLOps cho LLM
- Microsoft Learn: AI-102, AI-050

### Community
- LangChain Discord, Azure AI Foundry GitHub Discussions
- MCP GitHub: modelcontextprotocol/servers (reference implementations)
