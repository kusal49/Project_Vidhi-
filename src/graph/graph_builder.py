"""
Graph topology:
  [START]
     │
     ▼
  retrieval_node          ← Chroma MMR retrieval
     │
     ▼
  generation_node         ← Groq LLM + RAG prompt
     │
     ▼
  decision_node()         ← Conditional edge (not a node)
    │              │
    ▼              ▼
  email_node      END
    │
    ▼
   END

Usage:
    graph = build_legal_graph()
    result = graph.invoke(initial_state)
"""
from langgraph.graph import StateGraph, END

from .state import LegalAgentState
from .nodes import retrieval_node, generation_node, decision_node, email_node


def build_legal_graph() -> StateGraph:
    """
    Builds and compiles the legal notice StateGraph.
    Returns a compiled graph ready for .invoke().
    """
    builder = StateGraph(LegalAgentState)

    # Add nodes ────────────────────────────────────────────────────────
    builder.add_node("retrieval", retrieval_node)
    builder.add_node("generation", generation_node)
    builder.add_node("email", email_node)

    # Set entry point ───────────────────────────────────────────────────────
    builder.set_entry_point("retrieval")

    # Add edge: retrieval → generation ──────────────────────────────────
    builder.add_edge("retrieval", "generation")

    # Conditional edge: generation → (email | END) ─────────────────────────

    builder.add_conditional_edges(
        "generation",
        decision_node,
        {
            "email": "email",
            "end": END,
        },
    )

    # Terminal edge: email → END ────────────────────────────────────────────
    builder.add_edge("email", END)

    return builder.compile()
