"""Workflow state — shared between LangGraph nodes."""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class AgentId(str, Enum):
    """General-purpose platform — legal is just ONE domain agent."""

    GENERAL = "general-agent"
    DB_WORKER = "db-worker"
    RESEARCH_WORKER = "research-worker"
    ACTION_WORKER = "action-worker"
    CODE_WORKER = "code-worker"
    LEGAL_WORKER = "legal-agent"
    DEFAULT = "default-agent"


class TopologyMode(str, Enum):
    DIRECT = "direct"
    PLANNED = "planned"
    REVIEWED = "reviewed"
    COUNCIL = "council"


class IntentType(str, Enum):
    GREETING = "greeting"
    DB_ONLY = "db_only"
    GENERAL = "general"
    LEGAL = "legal"
    RESEARCH = "research"
    ACTION = "action"
    MULTI = "multi"
    BLOCKED = "blocked"


class TriageResult(BaseModel):
    intent: IntentType
    complexity: float = Field(ge=0.0, le=1.0, default=0.1)
    requires_planning: bool = False
    skip_review: bool = False
    skip_synthesize: bool = False
    fast_path: bool = False
    blocked: bool = False
    block_reason: str = ""
    security_flags: list[str] = Field(default_factory=list)


class PipelineStep(BaseModel):
    id: str
    phase: str  # triage | plan | worker | review | synthesize | eval
    agent: str | None = None
    status: Literal["running", "done", "skipped", "failed"] = "done"
    title: str
    detail: str = ""
    tools: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()


class EvalResult(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    checks: list[dict] = Field(default_factory=list)


class SubTask(BaseModel):
    id: str
    description: str
    assigned_agent: AgentId
    depends_on: list[str] = Field(default_factory=list)
    status: Literal["pending", "running", "done", "failed"] = "pending"
    task_kind: str = ""
    tool_id: str = ""
    tool_arguments: dict = Field(default_factory=dict)
    high_accuracy: bool = False


class ChatAttachment(BaseModel):
    """Image/file attachment from chat UI — OCR reads via image_base64."""

    filename: str = "attachment"
    mime_type: str = "application/octet-stream"
    data: str = Field(..., description="Base64 (with or without data:... prefix)")


class TaskPlan(BaseModel):
    main_task: str
    subtasks: list[SubTask]
    complexity_score: float = Field(ge=0.0, le=1.0)
    topology_mode: TopologyMode = TopologyMode.PLANNED
    is_greeting: bool = False


class WorkerResult(BaseModel):
    task_id: str
    agent: AgentId
    summary: str
    success: bool = True
    sources: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)


class GraphState(TypedDict):
    user_message: str
    session_id: str
    user_id: str
    trace_id: str
    chat_history: list[dict]
    attachments: list[dict]
    triage: TriageResult | None
    plan: TaskPlan | None
    topology_mode: str
    worker_results: list[WorkerResult]
    review_status: Literal["pending", "pass", "fail", "skipped"]
    review_notes: str
    eval_result: EvalResult | None
    final_response: str
    redacted_types: list[str]
    citations: list[dict]
    pipeline_steps: Annotated[list[PipelineStep], operator.add]
