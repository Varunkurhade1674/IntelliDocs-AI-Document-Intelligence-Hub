from langgraph.graph import StateGraph, END
from .state import AgentState
from .retrieval_agent import retrieval_node
from .summarization_agent import summarization_node
from .verification_agent import verification_node
from .generation_agent import generation_node

def create_agent_graph():
    """Build and compile the multi-agent RAG workflow graph."""
    workflow = StateGraph(AgentState)
    
    # 1. Add all agent nodes to the graph
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("summarization", summarization_node)
    workflow.add_node("verification", verification_node)
    workflow.add_node("generation", generation_node)
    
    # 2. Define sequential flow starting from retrieval
    workflow.set_entry_point("retrieval")
    
    workflow.add_edge("retrieval", "summarization")
    workflow.add_edge("summarization", "verification")
    workflow.add_edge("verification", "generation")
    workflow.add_edge("generation", END)
    
    # 3. Compile the graph
    return workflow.compile()
