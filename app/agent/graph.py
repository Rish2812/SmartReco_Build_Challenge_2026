from langgraph.graph import StateGraph, END

from app.agent.nodes import (
    AgentState,
    analyze_activity,
    retrieve,
    grade_retrieval,
    should_retry,
    generate_copy,
)


def build_recommendation_graph():
    graph = StateGraph(AgentState)

    graph.add_node("analyze", analyze_activity)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade", grade_retrieval)
    graph.add_node("generate", generate_copy)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", should_retry, {"retrieve": "retrieve", "generate": "generate"})
    graph.add_edge("generate", END)

    return graph.compile()


_compiled_graph = None


def get_recommendation_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_recommendation_graph()
    return _compiled_graph
