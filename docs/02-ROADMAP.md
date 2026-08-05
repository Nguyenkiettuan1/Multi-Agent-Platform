# Implementation Roadmap

## Timeline Overview

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
Foundation   MVP          Multi-task    Enterprise    MLOps
(2 weeks)    (4 weeks)    (4 weeks)     (6 weeks)     (ongoing)
```

---

## Phase 0: Foundation (Weeks 1–2)

**Goal:** Set up the environment, scaffold the project, and run one simple agent.

### Deliverables

- [ ] Azure AI Foundry project + model deployment (GPT-4.1)
- [ ] Docker Compose: PostgreSQL 16 + Redis 7
- [ ] PostgreSQL migrations (`app` + `platform` schemas)
- [ ] PostgresSaver checkpointing (local = prod pattern)
- [ ] 1 agent: DB Agent with sql-mcp tool
- [ ] Local dev workflow documented

### Learning topics (Phase 0)

| Topic | Resources |
|-------|-----------|
| MCP Protocol | https://modelcontextprotocol.io |
| Foundry Hosted Agents | Microsoft Foundry docs |
| Agent design patterns | ReAct, Tool Use |
| Prompt engineering basics | System prompt, few-shot |

### Exit criteria

- Send the question "How many records are in table X?" → agent queries the DB and returns the correct answer
- Trace visible in App Insights

---

## Phase 1: MVP — Orchestrator + 2 Workers (Weeks 3–6)

**Goal:** Basic multi-agent with A2A; orchestrator coordinates DB + Research agents.

### Deliverables

- [ ] Orchestrator Agent (supervisor pattern)
- [ ] DB Agent (production-ready, parameterized queries)
- [ ] Research Agent (Azure AI Search + optional web search)
- [ ] A2A connections: Orchestrator → DB, Orchestrator → Research
- [ ] API Gateway (FastAPI) with Entra ID auth
- [ ] 2 Skills: `database-query`, `legal-research` (template)
- [ ] Basic eval suite (5–10 test cases)
- [ ] Human-in-the-loop for write operations

### Learning topics (Phase 1)

| Topic | Resources |
|-------|-----------|
| A2A Protocol | Google A2A spec + Foundry A2A tool |
| Supervisor pattern | LangGraph docs, multi-agent patterns |
| RAG fundamentals | Chunking, embedding, retrieval |
| Eval-driven development | Foundry batch eval |

### Exit criteria

- User asks a cross-domain question: "Find contract X and explain clause Y" → orchestrator calls the correct 2 agents
- Eval pass rate ≥ 80% on the test suite
- Response time P95 < 30s

---

## Phase 2: Multi-Task & Action Agent (Weeks 7–10)

**Goal:** Parallel task execution, action agent, expanded skills.

### Deliverables

- [ ] Parallel A2A dispatch in the orchestrator
- [ ] Task DAG state management (Redis + PostgreSQL)
- [ ] Action Agent (notifications, API calls)
- [ ] `api-mcp` server
- [ ] HITL approval workflow (web UI or Teams adaptive card)
- [ ] Session management (multi-turn conversations)
- [ ] 5+ domain skills
- [ ] Streaming responses (SSE/WebSocket)

### Learning topics (Phase 2)

| Topic | Resources |
|-------|-----------|
| Task orchestration | DAG execution, dependency resolution |
| Streaming | SSE, WebSocket, invocations_ws |
| HITL patterns | Approval gates, timeout handling |
| State machines | Conversation checkpointing |

### Exit criteria

- Complete multi-step workflow: query → analyze → notify (with approval)
- 3+ agents run in parallel within one request
- Skills hot-reload without redeploying the agent

---

## Phase 3: Enterprise Hardening (Weeks 11–16)

**Goal:** Production-ready: security, scale, compliance.

### Deliverables

- [ ] Row-level security for the DB agent (per user identity)
- [ ] Full audit log (every query, tool call)
- [ ] Rate limiting + quota per user/team
- [ ] Multi-environment (dev/staging/prod)
- [ ] VNet isolation (if needed)
- [ ] RBAC for agent management
- [ ] Disaster recovery plan
- [ ] Load testing (100 concurrent users)
- [ ] Documentation for the ops team

### Learning topics (Phase 3)

| Topic | Resources |
|-------|-----------|
| Azure private networking | VNet, private endpoints |
| Security best practices | OWASP for AI, prompt injection defense |
| Load testing | k6, Azure Load Testing |
| Compliance | Data residency, audit requirements |

### Exit criteria

- Penetration test passed (basic)
- 99.9% uptime SLA in staging for 2 weeks
- Complete audit trail for compliance review

---

## Phase 4: MLOps & Continuous Improvement (Ongoing)

**Goal:** Fine-tuning loop, continuous eval, agent optimization.

### Deliverables

- [ ] Trace harvesting → eval datasets (automated)
- [ ] Batch eval in CI/CD (regression gate)
- [ ] SFT pipeline for domain-specific model
- [ ] DPO for response quality
- [ ] RFT with grader for tool-calling accuracy
- [ ] A/B testing model versions
- [ ] Prompt optimizer integration
- [ ] Agent Optimizer scaffold
- [ ] Production monitoring dashboard

### Learning topics (Phase 4)

| Topic | Resources |
|-------|-----------|
| Fine-tuning (SFT/DPO/RFT) | Foundry finetuning skill |
| Grader design | Reward functions, calibration |
| Dataset curation | Trace → training pairs |
| Model evaluation | Benchmark design, statistical significance |

### Exit criteria

- Fine-tuned model outperforms base model by ≥ 10% on domain eval
- CI/CD blocks deploy if eval regression > 5%
- Monthly eval report generated automatically

---

## Milestone Summary

| Phase | Timeline | Key Output |
|-------|----------|------------|
| 0 | Weeks 1–2 | 1 agent + 1 MCP server running locally |
| 1 | Weeks 3–6 | Orchestrator + A2A + API Gateway |
| 2 | Weeks 7–10 | Multi-task + HITL + Action agent |
| 3 | Weeks 11–16 | Enterprise security + scale |
| 4 | Ongoing | Fine-tuning + continuous eval |

## Suggested team roles

| Role | Phase 0–1 | Phase 2–3 | Phase 4 |
|------|-----------|-----------|---------|
| AI Engineer | Lead agent dev | Multi-agent orchestration | Fine-tuning, eval |
| Backend Engineer | MCP servers, API | Gateway, state mgmt | CI/CD, monitoring |
| DevOps | Foundry setup | Multi-env, VNet | MLOps pipeline |
| Domain Expert | Skills authoring | Skills expansion | Eval case design |
| Security | — | Audit, RBAC | Compliance review |
