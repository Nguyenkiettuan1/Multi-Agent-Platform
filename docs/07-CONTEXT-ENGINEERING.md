# Context Engineering — Quản lý Context Window

> Chi tiết cách thiết kế, phân bổ, và tối ưu context window trong multi-agent system.

---

## 1. Vấn đề Context Window

| Vấn đề | Nguyên nhân | Hậu quả |
|--------|-------------|----------|
| **Blowup** | `full_history` mode, mọi agent thấy mọi message | Vượt 128K tokens ở step 15–20 |
| **Pollution** | Worker thấy conversation của worker khác | Confused reasoning, wrong tool calls |
| **Waste** | Dump raw tool output vào messages | 80% tokens là noise |
| **Lost plan** | Context truncated, mất master plan | Agent "quên" đang làm gì |

Tham chiếu: [Anthropic — 200K limit → external memory](https://www.anthropic.com/engineering/multi-agent-research-system)

---

## 2. Nguyên tắc thiết kế

### Principle 1: Isolation by Default
> Mỗi subagent nhận **chỉ sub-task description** + **tools** + **skills**. Không thấy full conversation.

### Principle 2: State, Not Messages
> Agents ghi kết quả vào **typed state keys**. Chỉ Synthesizer đọc aggregated state.

### Principle 3: Condense Before Transfer
> Tool results → summarize → state key. Raw output KHÔNG vào message history.

### Principle 4: Budget per Role
> Mỗi role có token budget. Overflow → summarize hoặc external memory.

### Principle 5: Plan Persistence
> Master plan luôn persist (external memory / state), survive context truncation.

---

## 3. Context Layers

```mermaid
flowchart TB
    subgraph L1["Layer 1: System Prompt (static)"]
        ROLE[Role definition]
        RULES[Rules & constraints]
        TOOLS[Tool descriptions]
    end

    subgraph L2["Layer 2: Skills (semi-static)"]
        SKILL[Domain skill content]
        REF[Reference docs / schema]
    end

    subgraph L3["Layer 3: Task Context (per-invocation)"]
        SUBTASK[Sub-task description]
        PLAN[Plan excerpt from state]
        PRIOR[Prior results from state keys]
    end

    subgraph L4["Layer 4: Working Memory (per-turn)"]
        MSG[Current turn messages]
        TOOL_RES[Tool results (current turn)]
    end

    subgraph L5["Layer 5: External Memory (persistent)"]
        EXT_PLAN[Full plan]
        EXT_FINDINGS[All findings]
        EXT_HISTORY[Summarized history]
    end

    L1 --> PROMPT[Final Prompt]
    L2 --> PROMPT
    L3 --> PROMPT
    L4 --> PROMPT
    L5 -.->|load on demand| L3
```

### Token allocation per layer

| Layer | Triage | Worker | Planner | Synthesizer |
|-------|--------|--------|---------|-------------|
| L1 System | 1K | 1.5K | 2K | 1.5K |
| L2 Skills | 0 | 2K | 1K | 1K |
| L3 Task | 1K | 2K | 4K | 8K |
| L4 Working | 2K | 8K | 8K | 12K |
| L5 External | 0 | 0 | 16K | 8K |
| **Total Budget** | **4K** | **16K** | **32K** | **32K** |

---

## 4. Shared State Schema

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages

class TaskNode(TypedDict):
    id: str
    description: str
    agent: str          # "db-worker" | "research-worker" | ...
    status: Literal["pending", "running", "done", "failed"]
    depends_on: list[str]

class WorkerResult(TypedDict):
    agent: str
    summary: str        # Condensed result (max 500 tokens)
    raw_ref: str        # Pointer to blob storage for full data
    sources: list[str]
    tokens_used: int

class AgentState(TypedDict):
    # --- Session ---
    session_id: str
    user_id: str
    trace_id: str
    slo_tier: Literal["standard", "premium", "critical"]

    # --- Planning (Meta-Planner) ---
    user_intent: str
    complexity_score: float
    topology_mode: Literal["direct", "planned", "reviewed", "council"]
    plan: str                           # Master plan text
    task_dag: list[TaskNode]

    # --- Worker Results (condensed) ---
    worker_results: dict[str, WorkerResult]  # key = task_id

    # --- Quality ---
    review_status: Literal["pending", "pass", "fail", "revise"]
    review_notes: str
    review_iteration: int               # max 3 retries

    # --- Messages (current agent only) ---
    messages: Annotated[list, add_messages]

    # --- Token tracking ---
    token_budget: dict[str, int]        # per-role remaining budget
    total_tokens_used: int
    total_cost_usd: float

    # --- Output ---
    final_response: str | None
    citations: list[dict] | None
```

### Quy tắc đọc/ghi state

| Agent | Đọc | Ghi |
|-------|-----|-----|
| Triage | `user_intent` | `complexity_score`, `topology_mode` |
| Planner | `user_intent`, `complexity_score` | `plan`, `task_dag` |
| Worker | `task_dag[task_id]`, `plan` (excerpt) | `worker_results[task_id]` |
| Reviewer | `worker_results`, `plan` | `review_status`, `review_notes` |
| Synthesizer | `worker_results` (all), `plan` | `final_response` |
| Citation | `final_response`, `worker_results[*].sources` | `citations`, `final_response` (updated) |

---

## 5. Context Isolation Pattern (Anthropic)

```python
async def invoke_worker(state: AgentState, task: TaskNode) -> WorkerResult:
    """Worker nhận ISOLATED context — không thấy full conversation."""

  isolated_context = {
        "sub_task": task["description"],
        "plan_excerpt": summarize(state["plan"], max_tokens=500),
        "prior_results": {
            dep_id: state["worker_results"][dep_id]["summary"]
            for dep_id in task.get("depends_on", [])
            if dep_id in state["worker_results"]
        },
        "skills": load_skills(task["agent"]),
        "tools": get_tools(task["agent"]),
    }

    result = await worker_agent.invoke(isolated_context)

    return WorkerResult(
        agent=task["agent"],
        summary=condense(result, max_tokens=500),
        raw_ref=store_blob(result),
        sources=extract_sources(result),
        tokens_used=result.usage.total_tokens,
    )
```

**Key:** Worker KHÔNG nhận `state["messages"]`. Chỉ nhận condensed prior results.

---

## 6. Summarization Strategies

### 6.1 Tool Result Condensing

```python
def condense_tool_result(raw: str, max_tokens: int = 500) -> str:
    """SQL result 10K rows → summary for state."""
    if count_tokens(raw) <= max_tokens:
        return raw
    # Strategy: keep schema + first 5 rows + count + stats
    return f"Query returned {row_count} rows. Sample:\n{first_5_rows}\n..."
```

### 6.2 History Summarization (between turns)

```python
# LangGraph pre_model_hook pattern
def pre_model_hook(state: AgentState) -> dict:
    messages = state["messages"]
    budget = state["token_budget"].get("current_role", 16000)

    if count_tokens(messages) > budget * 0.7:
        # Summarize older messages, keep recent
        split_point = find_last_human_turn(messages)
        old = messages[:split_point]
        recent = messages[split_point:]

        summary = summarize_messages(old, max_tokens=budget * 0.2)
        return {
            "messages": [
                SystemMessage(content=f"Previous context summary:\n{summary}"),
                *recent,
            ]
        }
    return {}
```

### 6.3 External Memory (long-horizon)

Khi context > 200K tokens (Anthropic Research pattern):

```python
async def persist_plan(state: AgentState) -> None:
    """Write plan to external memory before context truncation."""
    await memory_store.save(
        key=f"plan:{state['session_id']}",
        value=state["plan"],
        ttl=3600,
    )

async def load_plan(session_id: str) -> str:
    return await memory_store.get(f"plan:{session_id}")
```

---

## 7. LangGraph Integration

### Supervisor config

```python
from langgraph_supervisor import create_supervisor

supervisor = create_supervisor(
    agents=[db_worker, research_worker, action_worker],
    model="gpt-4.1",
    output_mode="last_message",        # CRITICAL: not full_history
    parallel_tool_calls=True,
    pre_model_hook=summarization_hook,
    state_schema=AgentState,
)
```

### `output_mode` comparison

| Mode | Behavior | Use |
|------|----------|-----|
| `last_message` | Supervisor chỉ thấy message cuối từ worker | **Production** |
| `full_history` | Supervisor thấy toàn bộ worker conversation | Debug only (log to LangSmith) |

---

## 8. Context Budget Enforcement

```python
class ContextBudgetMiddleware:
    """Enforce token budget per role before LLM call."""

    BUDGETS = {
        "triage": 4096,
        "domain_worker": 16384,
        "meta_planner": 32768,
        "reviewer": 16384,
        "synthesizer": 32768,
    }

    async def before_model(self, state: AgentState, role: str) -> AgentState:
        budget = self.BUDGETS[role]
        used = count_tokens(state["messages"])

        if used > budget:
            state = await self.summarize_and_trim(state, budget)
            state["token_budget"][role] = 0  # exhausted
        else:
            state["token_budget"][role] = budget - used

        return state
```

---

## 9. Anti-patterns Checklist

- [ ] ❌ Pass `state["messages"]` to workers
- [ ] ❌ Use `output_mode="full_history"` in production
- [ ] ❌ Store raw SQL results (10K rows) in messages
- [ ] ❌ No token budget per role
- [ ] ❌ No summarization between long conversations
- [ ] ❌ No external memory for plans
- [ ] ❌ Workers can see each other's full conversation
- [ ] ✅ Condensed results in `worker_results` state keys
- [ ] ✅ `last_message` mode in production
- [ ] ✅ Plan persisted to external memory
- [ ] ✅ Per-role token budget with overflow handling
