from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    # Inputs
    query: str
    chat_history: List[Dict[str, Any]]
    vector_store: Any
    provider: str
    model: str
    temperature: float
    
    # Outputs/Intermediate steps
    retrieved_docs: List[Any]
    relevance_scores: List[int]
    summarized_context: str
    verification_report: Dict[str, Any]
    final_answer: str
    sources: List[Dict[str, Any]]
