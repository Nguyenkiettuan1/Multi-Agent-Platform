# GitHub Reference Map — Kiến trúc ↔ Nguồn code

> Mỗi quyết định kiến trúc PHANLAW đều có **nguồn tham chiếu cụ thể** từ repo/pattern production trên GitHub hoặc blog engineering chính thức.

---

## 1. Bản đồ quyết định kiến trúc

| # | Quyết định PHANLAW | Nguồn tham chiếu | Repo / Link | PHANLAW file |
|---|-------------------|------------------|-------------|--------------|
| 1 | 3-Plane (Control / Execution / Intelligence) | Mercor Enterprise Agent Architecture | [Blog](https://www.mercor.com/blog/the-three-planes-of-enterprise-agent-systems/) | `docs/01-ARCHITECTURE.md` |
| 2 | Supervisor multi-agent | LangGraph Supervisor | [langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py) | `agents/orchestrator/` |
| 3 | Stateful workflow + checkpoint | LangGraph | [langgraph](https://github.com/langchain-ai/langgraph) | `platform/checkpointer.py` |
| 4 | PostgreSQL checkpoint (local = prod) | LangGraph checkpoint-postgres | [checkpoint-postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres) | `docs/09-INFRASTRUCTURE.md` |
| 5 | Context isolation per subagent | Anthropic Engineering | [Multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system) | `docs/07-CONTEXT-ENGINEERING.md` |
| 6 | `output_mode=last_message` | LangGraph Supervisor docs | [create_supervisor](https://reference.langchain.com/python/langgraph-supervisor/supervisor/create_supervisor) | `docs/07-CONTEXT-ENGINEERING.md` |
| 7 | Model tier per role | OpenAI Swarm + RouteLLM | [swarm](https://github.com/openai/swarm), [RouteLLM](https://github.com/lm-sys/RouteLLM) | `docs/06-MODEL-TIERING.md` |
| 8 | Council mode (high-stakes) | Karpathy llm-council | [llm-council](https://github.com/karpathy/llm-council) | `docs/01-ARCHITECTURE.md` Mode 4 |
| 9 | MCP tool protocol | Anthropic MCP | [modelcontextprotocol](https://github.com/modelcontextprotocol) | `mcp-servers/` |
| 10 | MCP server examples | Official MCP servers | [servers](https://github.com/modelcontextprotocol/servers) | `mcp-servers/sql-server/` |
| 11 | A2A inter-agent | Google A2A | [A2A](https://github.com/google/A2A) | `docs/04-A2A-MCP-GUIDE.md` |
| 12 | Handoff vs agents-as-tools | OpenAI Agents SDK | [openai-agents-python](https://github.com/openai/openai-agents-python) | `agents/orchestrator/agent.yaml` |
| 13 | Role-based agent teams | CrewAI | [crewAI](https://github.com/crewAIInc/crewAI) | `skills/`, agent roles |
| 14 | Sequential/Parallel graphs | Google ADK | [adk-python](https://github.com/google/adk-python) | Pipeline mode |
| 15 | Enterprise .NET/Python SDK | Microsoft Agent Framework | [agent-framework](https://github.com/microsoft/agent-framework) | `infra/azure.yaml` |
| 16 | Multi-agent conversation | AutoGen | [autogen](https://github.com/microsoft/autogen) | Reference only |
| 17 | Per-step model routing | CASTER paper | [arXiv:2601.19793](https://arxiv.org/pdf/2601.19793v1) | Phase 4 roadmap |
| 18 | Observability / tracing | Langfuse | [langfuse](https://github.com/langfuse/langfuse) | `requirements.txt` (planned) |
| 19 | LLM proxy + fallbacks | LiteLLM | [litellm](https://github.com/BerriAI/litellm) | Model router layer |
| 20 | Eval-driven development | OpenAI evals | [openai-evals](https://github.com/openai/evals) | `eval/cases/` |
| 21 | RAG pipeline | LangChain | [langchain](https://github.com/langchain-ai/langchain) | `research-agent` (planned) |
| 22 | Guardrails | Guardrails AI | [guardrails](https://github.com/guardrails-ai/guardrails) | Control Plane (planned) |
| 23 | Prompt optimization | DSPy | [dspy](https://github.com/stanfordnlp/dspy) | Intelligence Plane (planned) |
| 24 | Deep agents (plan + subagents) | LangChain Deep Agents | [deepagents](https://github.com/langchain-ai/deepagents) | Meta-Planner pattern |
| 25 | PostgreSQL local → cloud | LangGraph deploy guides | [Deploy tutorial](https://rapidclaw.dev/blog/deploy-langgraph-production-tutorial-2026) | `docker-compose.yml` |

---

## 2. Danh mục GitHub theo chức năng

### Orchestration & State

| Repo | Stars | Học gì | Dùng ở PHANLAW |
|------|-------|---------|----------------|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 20K+ | Graph runtime, checkpointing, HITL | **Core workflow engine** |
| [langchain-ai/langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py) | — | Supervisor pattern | Orchestrator |
| [langchain-ai/langgraph-checkpoint-postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres) | — | PostgresSaver | `platform/checkpointer.py` |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 35K+ | Role + Task + Crew | Rapid prototype Phase 0 |
| [google/adk-python](https://github.com/google/adk-python) | — | Sequential/Parallel/Loop | Pipeline mode |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 45K+ | Multi-agent conversation | Reference |
| [microsoft/agent-framework](https://github.com/microsoft/agent-framework) | New | Enterprise SDK, MCP+A2A | Azure integration |

### Tools & Protocols

| Repo | Học gì | Dùng ở PHANLAW |
|------|---------|----------------|
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP server SDK | `mcp-servers/sql-server/` |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | Reference MCP servers | sql, search patterns |
| [google/A2A](https://github.com/google/A2A) | Agent-to-Agent protocol | Inter-agent communication |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | Handoffs, agents-as-tools | Triage routing |
| [openai/swarm](https://github.com/openai/swarm) | Educational handoff pattern | Model tier per agent |

### Model Routing & Cost

| Repo | Học gì | Dùng ở PHANLAW |
|------|---------|----------------|
| [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) | Strong/weak model routing | Control Plane router |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | Unified LLM API, fallbacks | Model proxy layer |

### Quality & Consensus

| Repo | Học gì | Dùng ở PHANLAW |
|------|---------|----------------|
| [karpathy/llm-council](https://github.com/karpathy/llm-council) | 3-stage council deliberation | Council mode (critical SLO) |
| [openai/evals](https://github.com/openai/evals) | Eval framework patterns | `eval/cases/` |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | Tracing, eval, datasets | Observability |
| [guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails) | Output validation | Control Plane guardrails |

### RAG & Knowledge

| Repo | Học gì | Dùng ở PHANLAW |
|------|---------|----------------|
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | RAG, retrievers, embeddings | Research agent |
| [run-llama/llama_index](https://github.com/run-llama/llama_index) | Alternative RAG framework | Reference |
| [chroma-core/chroma](https://github.com/chroma-core/chroma) | Vector DB (local dev) | Local vector store |
| [pgvector/pgvector](https://github.com/pgvector/pgvector) | Vector in PostgreSQL | **Cloud: vectors in same PG** |

### Infrastructure & Deploy

| Repo | Học gì | Dùng ở PHANLAW |
|------|---------|----------------|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) (deploy) | Production deploy patterns | Cloud deploy |
| [docker/awesome-compose](https://github.com/docker/awesome-compose) | Docker compose patterns | `docker-compose.yml` |
| [Azure-Samples/azure-search-openai-demo](https://github.com/Azure-Samples/azure-search-openai-demo) | Azure RAG reference | Cloud RAG pattern |

### Awesome Lists (đọc để khảo sát thêm)

| Repo | Mô tả |
|------|--------|
| [e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) | Curated AI agent list |
| [kyrolin/awesome-agentic-ai](https://github.com/kyrolin/awesome-agentic-ai) | Agentic AI resources |
| [WooooDyy/AgentGym](https://github.com/WooooDyy/AgentGym) | Agent benchmarks |
| [langchain-ai/langgraph-101](https://github.com/langchain-ai/langgraph-101) | LangGraph tutorials |

---

## 3. PostgreSQL — Nguồn tham chiếu

| Pattern | Nguồn | PHANLAW |
|---------|-------|---------|
| PostgresSaver checkpoint | [langgraph-checkpoint-postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres) | `platform/checkpointer.py` |
| AsyncPostgresSaver + pool | [LangGraph reference](https://langchain-ai.github.io/langgraph/reference/checkpoints/) | Production config |
| Local = Prod checkpointer | [ActiveWizards blog](https://activewizards.com/blog/langgraph-state-management-checkpointing-recovery-and-the-persistence-layer-decision/) | **Không dùng SQLite** |
| pgvector for RAG | [pgvector](https://github.com/pgvector/pgvector) | Phase 2: vectors in PostgreSQL |
| Read-only DB role | PostgreSQL RBAC best practice | `infra/database/migrations/004_roles.sql` |
| Docker local Postgres | [docker-compose postgres](https://hub.docker.com/_/postgres) | `docker-compose.yml` |
| Azure PostgreSQL migrate | [Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/) | `docs/09-INFRASTRUCTURE.md` |

---

## 4. Kiến trúc tổng hợp — Nguồn gốc từng layer

```
┌─────────────────────────────────────────────────────────────────┐
│ CLIENT                                                          │
│   Web / Teams / API                                             │
├─────────────────────────────────────────────────────────────────┤
│ CONTROL PLANE                                                   │
│   Model Router ←── RouteLLM, LiteLLM                            │
│   Policy/Guardrails ←── Guardrails AI, Azure Prompt Shields     │
│   RBAC ←── Entra ID                                             │
├─────────────────────────────────────────────────────────────────┤
│ EXECUTION PLANE                                                 │
│   Workflow Engine ←── LangGraph + langgraph-supervisor-py       │
│   Agent Fleet ←── OpenAI Agents SDK (handoff pattern)           │
│   MCP Tools ←── modelcontextprotocol/servers                    │
│   A2A Gateway ←── google/A2A                                    │
│   State ←── PostgresSaver (checkpoint-postgres)                 │
├─────────────────────────────────────────────────────────────────┤
│ DATA PLANE                                                      │
│   PostgreSQL app schema ←── Business data (contracts, clients)  │
│   PostgreSQL platform schema ←── Checkpoints, audit, DAG        │
│   Redis ←── Session cache                                       │
│   pgvector (Phase 2) ←── Embeddings in PostgreSQL               │
├─────────────────────────────────────────────────────────────────┤
│ INTELLIGENCE PLANE                                              │
│   Skills ←── Cursor Skills pattern                              │
│   Eval ←── openai/evals, Langfuse                               │
│   Fine-tune ←── Azure AI Foundry                                │
│   Council ←── karpathy/llm-council (critical tier)              │
├─────────────────────────────────────────────────────────────────┤
│ OBSERVABILITY                                                   │
│   Traces ←── Langfuse, OpenTelemetry, App Insights              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Lộ trình đọc code GitHub (8 tuần)

| Tuần | Đọc repo | Mục tiêu |
|------|----------|----------|
| 1 | `modelcontextprotocol/servers`, `python-sdk` | Hiểu MCP, build sql-mcp |
| 2 | `langchain-ai/langgraph`, `langgraph-101` | Graph, state, checkpoint |
| 3 | `langgraph-supervisor-py`, `openai/swarm` | Multi-agent patterns |
| 4 | `lm-sys/RouteLLM`, `BerriAI/litellm` | Model routing |
| 5 | Anthropic blog + `karpathy/llm-council` | Isolation + Council |
| 6 | `langgraph-checkpoint-postgres` + `docker-compose` | PostgreSQL local setup |
| 7 | `crewAI` hoặc `google/adk-python` | So sánh orchestration styles |
| 8 | `langfuse`, `openai/evals` | Eval + observability |

---

## 6. Quy tắc khi thêm component mới

Trước khi thêm bất kỳ pattern/library nào:

1. **Tìm repo reference** trên GitHub (ưu tiên >1K stars hoặc official)
2. **Ghi vào bảng Section 1** — quyết định ↔ nguồn
3. **Chỉ adopt pattern**, không copy toàn bộ repo
4. **Test trên PostgreSQL local** trước khi cloud
5. **Thêm eval case** cho behavior mới
