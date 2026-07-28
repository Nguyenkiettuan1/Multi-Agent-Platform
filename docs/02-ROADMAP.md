# Roadmap triển khai

## Tổng quan timeline

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
Foundation   MVP          Multi-task    Enterprise    MLOps
(2 tuần)    (4 tuần)     (4 tuần)      (6 tuần)      (ongoing)
```

---

## Phase 0: Foundation (Tuần 1–2)

**Mục tiêu:** Setup môi trường, scaffold project, chạy được 1 agent đơn giản.

### Deliverables

- [ ] Azure AI Foundry project + model deployment (GPT-4.1)
- [ ] Docker Compose: PostgreSQL 16 + Redis 7
- [ ] PostgreSQL migrations (`app` + `platform` schemas)
- [ ] PostgresSaver checkpointing (local = prod pattern)
- [ ] 1 agent: DB Agent với sql-mcp tool
- [ ] Local dev workflow documented

### Kiến thức cần học (Phase 0)

| Topic | Tài liệu |
|-------|----------|
| MCP Protocol | https://modelcontextprotocol.io |
| Foundry Hosted Agents | Microsoft Foundry docs |
| Agent design patterns | ReAct, Tool Use |
| Prompt engineering basics | System prompt, few-shot |

### Exit criteria

- Gửi câu hỏi "Có bao nhiêu bản ghi trong bảng X?" → agent query DB và trả lời đúng
- Trace visible trong App Insights

---

## Phase 1: MVP — Orchestrator + 2 Workers (Tuần 3–6)

**Mục tiêu:** Multi-agent cơ bản với A2A, orchestrator điều phối DB + Research agents.

### Deliverables

- [ ] Orchestrator Agent (supervisor pattern)
- [ ] DB Agent (production-ready, parameterized queries)
- [ ] Research Agent (Azure AI Search + optional web search)
- [ ] A2A connections: Orchestrator → DB, Orchestrator → Research
- [ ] API Gateway (FastAPI) với Entra ID auth
- [ ] 2 Skills: `database-query`, `legal-research` (template)
- [ ] Basic eval suite (5–10 test cases)
- [ ] Human-in-the-loop cho write operations

### Kiến thức cần học (Phase 1)

| Topic | Tài liệu |
|-------|----------|
| A2A Protocol | Google A2A spec + Foundry A2A tool |
| Supervisor pattern | LangGraph docs, multi-agent patterns |
| RAG fundamentals | Chunking, embedding, retrieval |
| Eval-driven development | Foundry batch eval |

### Exit criteria

- User hỏi cross-domain: "Tìm hợp đồng X và giải thích điều khoản Y" → orchestrator gọi đúng 2 agents
- Eval pass rate ≥ 80% trên test suite
- Response time P95 < 30s

---

## Phase 2: Multi-Task & Action Agent (Tuần 7–10)

**Mục tiêu:** Parallel task execution, action agent, skills mở rộng.

### Deliverables

- [ ] Parallel A2A dispatch trong orchestrator
- [ ] Task DAG state management (Redis + PostgreSQL)
- [ ] Action Agent (notifications, API calls)
- [ ] `api-mcp` server
- [ ] HITL approval workflow (web UI hoặc Teams adaptive card)
- [ ] Session management (multi-turn conversations)
- [ ] 5+ domain skills
- [ ] Streaming responses (SSE/WebSocket)

### Kiến thức cần học (Phase 2)

| Topic | Tài liệu |
|-------|----------|
| Task orchestration | DAG execution, dependency resolution |
| Streaming | SSE, WebSocket, invocations_ws |
| HITL patterns | Approval gates, timeout handling |
| State machines | Conversation checkpointing |

### Exit criteria

- Multi-step workflow hoàn chỉnh: query → analyze → notify (với approval)
- 3+ agents chạy parallel trong 1 request
- Skills hot-reload không cần redeploy agent

---

## Phase 3: Enterprise Hardening (Tuần 11–16)

**Mục tiêu:** Production-ready: security, scale, compliance.

### Deliverables

- [ ] Row-level security cho DB agent (theo user identity)
- [ ] Audit log đầy đủ (mọi query, tool call)
- [ ] Rate limiting + quota per user/team
- [ ] Multi-environment (dev/staging/prod)
- [ ] VNet isolation (nếu cần)
- [ ] RBAC cho agent management
- [ ] Disaster recovery plan
- [ ] Load testing (100 concurrent users)
- [ ] Documentation cho ops team

### Kiến thức cần học (Phase 3)

| Topic | Tài liệu |
|-------|----------|
| Azure private networking | VNet, private endpoints |
| Security best practices | OWASP for AI, prompt injection defense |
| Load testing | k6, Azure Load Testing |
| Compliance | Data residency, audit requirements |

### Exit criteria

- Penetration test passed (basic)
- 99.9% uptime SLA trong staging 2 tuần
- Audit trail đầy đủ cho compliance review

---

## Phase 4: MLOps & Continuous Improvement (Ongoing)

**Mục tiêu:** Fine-tuning loop, continuous eval, agent optimization.

### Deliverables

- [ ] Trace harvesting → eval datasets (automated)
- [ ] Batch eval trong CI/CD (regression gate)
- [ ] SFT pipeline cho domain-specific model
- [ ] DPO cho response quality
- [ ] RFT với grader cho tool-calling accuracy
- [ ] A/B testing model versions
- [ ] Prompt optimizer integration
- [ ] Agent Optimizer scaffold
- [ ] Production monitoring dashboard

### Kiến thức cần học (Phase 4)

| Topic | Tài liệu |
|-------|----------|
| Fine-tuning (SFT/DPO/RFT) | Foundry finetuning skill |
| Grader design | Reward functions, calibration |
| Dataset curation | Trace → training pairs |
| Model evaluation | Benchmark design, statistical significance |

### Exit criteria

- Fine-tuned model outperform base model ≥ 10% trên domain eval
- CI/CD block deploy nếu eval regression > 5%
- Monthly eval report tự động

---

## Milestone Summary

| Phase | Timeline | Key Output |
|-------|----------|------------|
| 0 | Tuần 1–2 | 1 agent + 1 MCP server chạy local |
| 1 | Tuần 3–6 | Orchestrator + A2A + API Gateway |
| 2 | Tuần 7–10 | Multi-task + HITL + Action agent |
| 3 | Tuần 11–16 | Enterprise security + scale |
| 4 | Ongoing | Fine-tuning + continuous eval |

## Team roles đề xuất

| Role | Phase 0–1 | Phase 2–3 | Phase 4 |
|------|-----------|-----------|---------|
| AI Engineer | Lead agent dev | Multi-agent orchestration | Fine-tuning, eval |
| Backend Engineer | MCP servers, API | Gateway, state mgmt | CI/CD, monitoring |
| DevOps | Foundry setup | Multi-env, VNet | MLOps pipeline |
| Domain Expert | Skills authoring | Skills expansion | Eval case design |
| Security | — | Audit, RBAC | Compliance review |
