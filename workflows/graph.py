"""Build and compile LangGraph workflow."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from workflows.nodes.pipeline import (
    eval_node,
    execute_workers_node,
    plan_node,
    review_node,
    route_after_execute,
    route_after_triage,
    synthesize_node,
    triage_node,
)
from workflows.state import GraphState


def build_graph(checkpointer=None):
    """Adaptive pipeline with optional checkpointer for session persistence."""
    graph = StateGraph(GraphState)

    graph.add_node("triage", triage_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute_workers", execute_workers_node)
    graph.add_node("review", review_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("eval", eval_node)

    graph.add_edge(START, "triage")
    graph.add_conditional_edges("triage", route_after_triage, {"plan": "plan", "eval": "eval"})
    graph.add_edge("plan", "execute_workers")
    graph.add_conditional_edges(
        "execute_workers",
        route_after_execute,
        {"eval": "eval", "review": "review", "synthesize": "synthesize"},
    )
    graph.add_edge("review", "synthesize")
    graph.add_edge("synthesize", "eval")
    graph.add_edge("eval", END)

    return graph.compile(checkpointer=checkpointer)
