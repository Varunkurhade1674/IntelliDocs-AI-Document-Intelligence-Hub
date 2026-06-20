from typing import Dict, Any, List
from .state import AgentState
from .utils import get_llm
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def generation_node(state: AgentState) -> Dict[str, Any]:
    query = state["query"]
    summary = state["summarized_context"]
    report = state["verification_report"]
    docs = state["retrieved_docs"]
    chat_history = state["chat_history"]
    
    # 1. Compile sources metadata
    sources = []
    for d in docs:
        src = d.metadata.get("source", "Document")
        pg = d.metadata.get("page", "—")
        sources.append({"file": src, "page": pg, "text": d.page_content})
        
    llm = get_llm(state["provider"], state["model"], state["temperature"])
    
    # 2. Build instructions incorporating fact check warnings
    unsupported_str = ""
    if report.get("status") == "WARNING" and report.get("unsupported_claims"):
        unsupported_str = f"WARNING: Avoid making the following unsupported claims: {', '.join(report['unsupported_claims'])}"
        
    system_prompt = (
        "You are the Answer Generation Agent for IntelliDocs AI.\n"
        "Your task is to draft a comprehensive, professional, and clear answer to the user's query.\n"
        "Instructions:\n"
        "1. Base your answer strictly on the Summarized Context below.\n"
        "2. Make sure you do NOT include any unsupported claims or hallucinations.\n"
        "3. You must use clear markdown formatting (bold terms, lists, tables, headers).\n"
        "4. Include inline source citations referencing the document name and page number "
        "(e.g., [Source: file.pdf, Page: 4]) when stating facts.\n"
        "5. If the context does not contain enough information, state: 'The provided documents do not contain information to answer this query.'\n\n"
        f"--- SUMMARIZED CONTEXT ---\n{summary}\n\n"
        f"{unsupported_str}"
    )
    
    # 3. Build messages list (Memory integration)
    msgs = [SystemMessage(content=system_prompt)]
    
    # Keep last 10 messages from chat history to avoid context window congestion
    for m in chat_history[-10:]:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        else:
            # Avoid feeding source metadata dictionaries directly into text messages
            msgs.append(AIMessage(content=m["content"]))
            
    msgs.append(HumanMessage(content=query))
    
    # 4. Invoke LLM to generate the final response
    try:
        resp = llm.invoke(msgs)
        final_answer = resp.content.strip()
    except Exception as e:
        final_answer = f"Error generating response: {e}"
        
    return {
        "final_answer": final_answer,
        "sources": sources
    }
