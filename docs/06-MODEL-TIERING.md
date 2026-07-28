# Model Tiering & Routing

> Chi tiết cách phân cấp model, route request, và tối ưu cost/quality.

---

## 1. Tại sao cần Model Tiering?

**Sai lầm phổ biến:** Dùng 1 model (GPT-4) cho mọi agent → chi phí ×10, latency ×3, không cần thiết.

**Thực tế production:**
- 60% requests chỉ cần classify/route → model rẻ (mini)
- 25% cần tool use + reasoning vừa → model balanced (sonnet/4.1)
- 10% cần planning/synthesis phức tạp → model mạnh (opus/o3)
- 5% cần multi-model consensus → council mode

Tham chiếu: [RouteLLM — 85% cost reduction](https://github.com/lm-sys/RouteLLM), [OpenAI Swarm — cheap model for triage](https://github.com/openai/swarm)

---

## 2. Model Tier Definitions

### Tier Matrix

| Tier | Name | Models (Azure) | Input $/1M | Relative Cost | Max Latency | Capabilities |
|------|------|----------------|------------|---------------|-------------|--------------|
| **T0** | Fast | gpt-4o-mini, haiku-3.5 | ~$0.15 | 1× | 2s | Classify, route, format, extract |
| **T1** | Balanced | gpt-4.1, sonnet-4 | ~$2.50 | 15× | 5s | Tool use, SQL, search, analysis |
| **T2** | Reasoning | o3, claude-opus-4 | ~$15 | 100× | 15s | Planning, synthesis, complex reasoning |
| **T3** | Council | 3+ models + chairman | ~$30+ | 200× | 30s | High-stakes consensus |

### Role → Tier Mapping (default)

```yaml
role_model_mapping:
  triage:           T0
  micro_worker:     T0
  domain_worker:    T1
  reviewer:         T1    # KHÔNG dùng T0 cho review
  citation_agent:   T1
  meta_planner:     T2
  synthesizer:      T2
  chairman:         T2
```

---

## 3. Ba cơ chế Routing

### 3.1 Role-based (Static) — Default

Model cố định theo agent role. Predictable, auditable.

```python
ROLE_TIER = {
    "triage": "T0",
    "db-worker": "T1",
    "meta-planner": "T2",
}
```

**Ưu:** Đơn giản, dễ debug, dễ audit.
**Nhược:** Không tối ưu per-query.

### 3.2 Query-based (Dynamic) — RouteLLM

Classifier đánh giá complexity mỗi request, route strong/weak model.

```
Request → BERT Classifier → complexity_score
  if score > threshold → T2 (strong)
  else → T0/T1 (weak)
```

Tham chiếu: [RouteLLM](https://github.com/lm-sys/RouteLLM)

```python
from routellm.controller import Controller

router = Controller(
    routers=["mf"],  # Matrix Factorization
    strong_model="gpt-4.1",
    weak_model="gpt-4o-mini",
)

# 11% requests route to strong model at this threshold
response = router.chat.completions.create(
    model="router-mf-0.11",
    messages=[...],
)
```

**Kết quả RouteLLM:**
- 85% cost reduction (MT-Bench)
- 95% quality of always-strong
- <10ms routing decision (BERT classifier)

### 3.3 Step-based (Per-node) — CASTER

Trước MỖI node trong LangGraph workflow, router quyết định tier.

```
Graph execution:
  Node: planner → Router: T2 (complexity=0.9)
  Node: db-worker → Router: T1 (tool_use)
  Node: format → Router: T0 (simple)
  Node: reviewer → Router: T1 (review failed at T0 → upgrade to T1)
```

**Ưu:** Tối ưu nhất, adaptive.
**Nhược:** Phức tạp, cần LangGraph integration.

---

## 4. Routing Decision Tree

```
Incoming Request
  │
  ├─ SLO tier = "critical"?
  │   └─ YES → Council Mode (T3)
  │
  ├─ Triage (T0): classify intent + complexity
  │   ├─ complexity < 0.3 → Direct Worker (T0/T1)
  │   ├─ complexity 0.3–0.7 → Planned (T1 workers + T2 planner)
  │   └─ complexity > 0.7 → Full pipeline (T2 planner + T1 workers + T1 reviewer + T2 synth)
  │
  ├─ Data sensitivity = "confidential"?
  │   └─ YES → Restrict to on-prem / private endpoint models only
  │
  └─ Token budget exhausted?
      └─ YES → Downgrade tier OR summarize + continue
```

---

## 5. Cost Model (ví dụ)

### Per-request cost estimate

| Topology | Agents | Avg Tokens | Est. Cost |
|----------|--------|------------|-----------|
| Direct (T0→T1) | 2 | 3K | $0.005 |
| Planned (T0→T2→T1×2→T2) | 5 | 15K | $0.04 |
| Reviewed (+T1 reviewer) | 6 | 18K | $0.05 |
| Council (T0→T2→T1×3→T3→T2) | 8+ | 50K | $0.15 |

### Monthly projection (10K requests/month)

| Mix | Cost/month |
|-----|------------|
| All T2 (no routing) | ~$1,500 |
| With tiering (60/30/8/2) | ~$300 |
| Savings | **80%** |

---

## 6. Implementation Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Classifier | RouteLLM BERT router | Per-query complexity |
| Proxy | LiteLLM | Unified API, fallback chains |
| Role mapping | Custom config (agent.yaml) | Static tier per role |
| Step router | LangGraph pre_model_hook | Per-node tier decision |
| Observability | Langfuse / App Insights | Log every routing decision |
| Feedback | User thumbs + eval | Retrain router over time |

### LiteLLM fallback chain

```python
import litellm

response = litellm.completion(
    model="gpt-4.1",           # primary (T1)
    fallbacks=["gpt-4o-mini"], # fallback (T0) if T1 unavailable
    messages=[...],
    metadata={"role": "db-worker", "tier": "T1"},
)
```

---

## 7. Fine-tuning per Tier

| Tier | Fine-tune? | Method | Dataset |
|------|-----------|--------|---------|
| T0 | Yes (cheap) | SFT | Classification, routing examples |
| T1 | Yes | SFT + RFT | Tool-calling traces, domain Q&A |
| T2 | Selective | SFT | Planning, synthesis examples |
| T3 | No | Use base models | N/A |

**Strategy:** Fine-tune T1 workers cho domain PHANLAW (legal, contracts). Giữ T0/T2 dùng base models.

---

## 8. Monitoring Routing Quality

```yaml
# Metrics to track
routing_metrics:
  - routing_decision_latency_ms
  - tier_distribution: {T0: 60%, T1: 30%, T2: 8%, T3: 2%}
  - downgrade_rate: 5%        # T2→T1 due to budget
  - upgrade_rate: 3%          # T0→T1 due to failure
  - cost_per_request_usd
  - quality_by_tier:           # eval score per tier
      T0: 0.85
      T1: 0.93
      T2: 0.97
  - router_accuracy: 0.92     # vs human labels
```

**Alert:** Nếu `upgrade_rate > 10%` → router đang under-estimate complexity, cần retrain.
