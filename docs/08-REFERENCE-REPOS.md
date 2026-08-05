# Reference Repositories — Survey Frameworks & Patterns

> Survey of popular repos and patterns applicable to the Multi-Agent Platform.

---

## 1. Framework Comparison Matrix

| Framework | Stars | Language | Orchestration | State | MCP | A2A | Production | Best For |
|-----------|-------|----------|---------------|-------|-----|-----|------------|----------|
| **LangGraph** | 20K+ | Python | Graph-based | ✅ Durable | ✅ | ✅ | ✅ Klarna, Uber | Stateful workflows, fine control |
| **CrewAI** | 35K+ | Python | Role-based Crews | ✅ Flows | ✅ | ✅ | ✅ | Rapid prototyping, role teams |
| **Microsoft Agent Framework** | New | .NET/Python | Workflows + Harnesses | ✅ | ✅ Native | ✅ Native | Azure/Foundry enterprise |
| **Google ADK** | Growing | Py/TS/Go/Java | Sequential/Parallel/Loop | ✅ | ✅ | ✅ Native | ✅ Vertex AI | GCP, auditable graphs |
| **OpenAI Agents SDK** | — | Python | Handoffs | Session | ✅ | Partial | ✅ | OpenAI ecosystem |
| **AutoGen** | 45K+ | Python/.NET | Conversational | ✅ | ✅ | ✅ | ✅ | Microsoft shops, conversation |
| **llm-council** | 10K+ | Python | 3-stage pipeline | Stateless | ❌ | ❌ | Demo | Multi-model consensus |
| **RouteLLM** | 4K+ | Python | Router proxy | Stateless | ❌ | ❌ | ✅ | Cost optimization |

---

## 2. Repo Details

### 2.1 LangGraph — Orchestration Engine (RECOMMENDED)

- **Repo:** https://github.com/langchain-ai/langgraph
- **Docs:** https://docs.langchain.com/oss/python/langgraph/overview

**Strengths:**
- Low-level graph runtime — full control over agent flow
- Durable execution, checkpointing, human-in-the-loop
- `create_supervisor` for multi-agent with `output_mode`, `pre_model_hook`
- State schema (TypedDict) — typed shared state
- Production: Klarna, Uber, J.P. Morgan

**Patterns to learn:**
```
Supervisor pattern → output_mode="last_message"
State schema → worker_results keys, not full messages
pre_model_hook → summarization middleware
Parallel tool calls → parallel A2A dispatch
```

**Used in this project for:** Workflow engine, state management, supervisor orchestration.

---

### 2.2 Anthropic Multi-Agent Research — Architecture Reference

- **Blog:** https://www.anthropic.com/engineering/multi-agent-research-system

**Architecture:**
```
LeadResearcher (Opus) → plan → external memory
  ├── Subagent 1 (Sonnet) → isolated context → condensed findings
  ├── Subagent 2 (Sonnet) → isolated context → condensed findings
  └── Subagent N (Sonnet) → isolated context → condensed findings
LeadResearcher → synthesize → CitationAgent → final output
```

**Key lessons:**
- Lead agent ≠ worker agent (different models)
- Subagents: "almost nothing" about each other (isolation)
- External memory when > 200K tokens
- Citation agent as separate pass
- 90.2% improvement over single-agent

**Applied in this project:** Planner/Worker/Synthesizer/Citation role separation.

---

### 2.3 llm-council (Karpathy) — Council Pattern

- **Repo:** https://github.com/karpathy/llm-council
- **Docs:** https://llm-council.dev/architecture/overview/

**3-stage pipeline:**
```
Stage 1: Parallel Generation — all models answer independently
Stage 2: Anonymous Peer Review — models rank responses (A, B, C...)
Stage 3: Chairman Synthesis — designated model combines best elements
```

**Key lessons:**
- Anonymization prevents model favoritism
- Chairman ≠ any council member (designated synthesizer)
- Graceful degradation (continue if 1 model fails)
- 4-layer architecture: Tier Selection → Triage → Orchestration → Gateway

**Applied in this project:** Mode 4 (Council) for critical SLO tier.

---

### 2.4 RouteLLM — Model Routing

- **Repo:** https://github.com/lm-sys/RouteLLM
- **Paper:** arXiv 2406.18665

**Architecture:**
```
Request → Router (BERT/MF classifier) → strong model OR weak model
```

**Results:**
- 85% cost reduction (MT-Bench)
- 45% savings (MMLU)
- <10ms routing decision
- OpenAI-compatible proxy server

**Applied in this project:** Control Plane model router, T0/T1 dynamic routing.

---

### 2.5 OpenAI Agents SDK / Swarm — Handoff Pattern

- **Repo:** https://github.com/openai/swarm (educational)
- **SDK:** https://openai.github.io/openai-agents-python/

**Key patterns:**
```python
# Cheap model for triage
triage = Agent(model="gpt-4o-mini", handoffs=[billing, technical])

# Strong model for specialist
billing = Agent(model="gpt-4o", tools=[...])
```

**2 patterns:**
- **Handoffs:** Specialist owns conversation (customer support)
- **Agents as tools:** Manager stays in control, calls specialists (`agent.as_tool()`)

**Applied in this project:** Triage agent (T0), handoff vs agents-as-tools decision per use case.

---

### 2.6 CrewAI — Role-based Teams

- **Repo:** https://github.com/crewAIInc/crewAI

**Architecture:**
```
Crew = Agents (roles) + Tasks (sequential/parallel) + Process (sequential/hierarchical)
Flow = Event-driven workflows with state, branching
```

**Key concepts:**
- Agent = role + goal + backstory + tools + LLM
- Task = description + expected_output + agent assignment
- Process = sequential | hierarchical (manager agent)

**Applied in this project:** Role definition pattern, hierarchical process for planning.

---

### 2.7 Microsoft Agent Framework 1.0 — Enterprise SDK

- **Blog:** https://devblogs.microsoft.com/agent-framework/
- **GA:** April 3, 2026

**3 pillars:**
1. **Agent loops** — model + tools + state
2. **Workflows** — multi-step orchestration
3. **Harnesses** — memory, planning, middleware, controls

**Native:** MCP + A2A + Azure AI Foundry integration.

**Applied in this project:** If the team is .NET/Azure-heavy, consider MAF over raw LangGraph.

---

### 2.8 Google ADK — Graph Orchestration

- **Site:** https://adk.dev/

**Primitives:**
- `SequentialAgent` — A → B → C
- `ParallelAgent` — A || B || C
- `LoopAgent` — iterate until done

**Key philosophy:** Explicit graphs, auditable paths. "Point at the graph and tell an auditor exactly how a decision got made."

**Applied in this project:** Pipeline mode (ETL, reporting), A2A interop.

---

### 2.9 CASTER — Per-step Model Routing

- **Paper:** https://arxiv.org/pdf/2601.19793v1

**Innovation:** Dynamic interceptor before each LangGraph node:
```
Before agent node → CASTER analyzes state → selects model tier
If low-cost model fails → rollback + upgrade tier
```

**Applied in this project:** Advanced routing (Phase 4), per-step tier optimization.

---

## 3. Pattern Catalog — When to Use What

| Pattern | Source | Use Case | Execution mode |
|---------|--------|----------|--------------|
| Supervisor | LangGraph | Default orchestration | Mode 1–3 |
| Context Isolation | Anthropic | Parallel workers | All modes |
| Council | llm-council | High-stakes decisions | Mode 4 |
| Model Routing | RouteLLM | Cost optimization | Control Plane |
| Handoff | OpenAI Swarm | Specialist owns conversation | Support bot |
| Agents-as-Tools | OpenAI SDK | Manager synthesizes | Orchestrator |
| Hierarchical | CrewAI | Manager + workers | Planner → Workers |
| Pipeline | Google ADK | Deterministic ETL | Report generation |
| Map-Reduce | llm-council | Parallel + synthesize | Research tasks |
| Step Routing | CASTER | Per-node model selection | Phase 4 |

---

## 4. Recommended Stack

```
┌─────────────────────────────────────────────────┐
│ Orchestration:  LangGraph (state + supervisor)    │
│ Hosting:        Azure AI Foundry (deploy + eval)  │
│ Tools:          MCP (sql, search, api, file)      │
│ Inter-agent:    A2A (worker endpoints)            │
│ Model Router:   RouteLLM + role-based mapping     │
│ Observability:  Langfuse / App Insights           │
│ Eval:           Foundry batch eval + graders      │
│ Fine-tune:      Foundry SFT/DPO/RFT              │
│ Skills:         Markdown modules (Cursor-style)   │
│ Council:        llm-council pattern (critical tier)│
└─────────────────────────────────────────────────┘
```

### Why this stack?

| Choice | Alternative | Why chosen |
|--------|-------------|------------|
| LangGraph | CrewAI | Fine-grained state control, production-proven |
| Foundry | Self-hosted | Built-in A2A, MCP, eval, FT, enterprise governance |
| RouteLLM | Manual routing | 85% cost savings, proven classifier |
| llm-council pattern | Single reviewer | Multi-model consensus for legal decisions |
| MCP | Custom tools | Open standard, reusable, testable |
| A2A | In-process only | Independent deploy, scaling, team ownership |

---

## 5. Repos to Study (Learning Path)

### Week 1–2: Foundations
1. [MCP Specification](https://modelcontextprotocol.io) — tool protocol
2. [OpenAI Swarm](https://github.com/openai/swarm) — handoff basics
3. [RouteLLM](https://github.com/lm-sys/RouteLLM) — model routing

### Week 3–4: Multi-Agent
4. [LangGraph Supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) — supervisor pattern
5. [Anthropic Research blog](https://www.anthropic.com/engineering/multi-agent-research-system) — isolation pattern
6. [llm-council](https://github.com/karpathy/llm-council) — council pattern

### Week 5–6: Production
7. [LangGraph production deploy guide](https://octopusbuilds.com/blog/deploy-langgraph-production)
8. [Microsoft Agent Framework](https://devblogs.microsoft.com/agent-framework/) — enterprise SDK
9. [Google ADK](https://adk.dev/) — graph orchestration

### Week 7–8: Optimization
10. [CASTER paper](https://arxiv.org/pdf/2601.19793v1) — per-step routing
11. [Context Engineering blog](https://www.langchain.com/blog/context-engineering-for-agents)
12. [Foundry eval + fine-tuning docs](https://learn.microsoft.com/azure/foundry/)

---

## 6. Architecture Decision: Framework

| Criteria | LangGraph + Foundry | CrewAI | Microsoft AF | Google ADK |
|----------|-------------------|--------|-------------|------------|
| State management | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Multi-agent patterns | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| MCP native | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| A2A native | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Azure integration | ⭐⭐ (via Foundry) | ⭐ | ⭐⭐⭐ | ⭐ |
| Learning curve | Medium | Low | Medium | Medium |
| Production refs | Klarna, Uber | Many startups | Microsoft enterprise | Google Cloud |

**Decision: LangGraph (orchestration logic) + Azure AI Foundry (hosting/governance) + MCP + A2A**

CrewAI can be used for rapid prototyping in Phase 0, then migrate to LangGraph in Phase 1.
