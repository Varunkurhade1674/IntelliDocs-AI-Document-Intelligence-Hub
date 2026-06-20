from typing import Dict, Any
from .state import AgentState
from .utils import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

def summarization_node(state: AgentState) -> Dict[str, Any]:
    query = state["query"]
    docs = state["retrieved_docs"]
    
    if not docs:
        return {"summarized_context": "No relevant documents found."}
        
    context_str = ""
    for idx, d in enumerate(docs):
        src = d.metadata.get("source", "Document")
        pg = d.metadata.get("page", "—")
        context_str += f"--- CHUNK {idx+1} [Source: {src}, Page: {pg}] ---\n{d.page_content}\n\n"
        
    llm = get_llm(state["provider"], state["model"], state["temperature"])
    
    system_prompt = (
        "You are a Summarization Agent. Your task is to synthesize and condense the provided document chunks into a clean, "
        "structured, and cohesive context summary tailored to the user's query.\n"
        "Instructions:\n"
        "1. Filter out redundant information and noise while retaining all core facts, names, numbers, and key terms.\n"
        "2. Retain references/sources (e.g. filename and page numbers) for the facts you include.\n"
        "3. Format the summary cleanly using bullet points, bold text, or lists under relevant headings."
    )
    
    user_prompt = f"User Query: {query}\n\nDocument Chunks:\n{context_str}"
    
    try:
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        summarized_context = resp.content.strip()
    except Exception as e:
        # Fallback to direct raw context if LLM call fails
        summarized_context = f"Raw Context (Fallback):\n\n{context_str}"
        
    return {"summarized_context": summarized_context}
