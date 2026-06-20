import json
import re
from typing import Dict, Any
from .state import AgentState
from .utils import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

def retrieval_node(state: AgentState) -> Dict[str, Any]:
    query = state["query"]
    vs = state["vector_store"]
    
    # 1. Retrieve top 5 candidates
    raw_docs = []
    try:
        # Retry up to 3 times on network hiccups
        for attempt in range(3):
            try:
                raw_docs = vs.similarity_search(query, k=5)
                break
            except Exception as e:
                if attempt == 2:
                    raise e
    except Exception:
        raw_docs = []

    if not raw_docs:
        return {
            "retrieved_docs": [],
            "relevance_scores": []
        }
        
    # 2. Batch score relevance of chunks using LLM
    llm = get_llm(state["provider"], state["model"], 0.0) # Temperature 0 for rating accuracy
    
    chunks_str = ""
    for idx, d in enumerate(raw_docs):
        chunks_str += f"--- CHUNK {idx+1} ---\n{d.page_content}\n\n"
        
    system_prompt = (
        "You are a Relevance Scorer Agent. Your job is to evaluate if the retrieved document chunks are relevant to the user's query.\n"
        "Assign a relevance score from 0 to 5 for each chunk, where:\n"
        "0 - Completely irrelevant\n"
        "1 - Marginally related, but does not help answer the query\n"
        "3 - Partially relevant, contains some helpful context\n"
        "5 - Highly relevant, directly helps answer the query\n\n"
        "Response Format: Return ONLY a JSON list of integers corresponding to the score of each chunk in order. "
        "For example: [5, 1, 4, 0, 3]. Do NOT return any markdown formatting, code block fences, or explanations."
    )
    
    user_prompt = f"User Query: {query}\n\nDocument Chunks:\n{chunks_str}"
    
    relevance_scores = []
    try:
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        content = resp.content.strip()
        
        # Strip potential markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                content = "\n".join(lines[1:-1])
        content = content.strip()
        
        # Attempt to parse json list
        relevance_scores = json.loads(content)
        if not isinstance(relevance_scores, list) or len(relevance_scores) != len(raw_docs):
            # Try regex to extract digits list
            matches = re.findall(r'\d+', content)
            relevance_scores = [int(m) for m in matches]
    except Exception:
        # Fallback to default score if parsing or API fails
        relevance_scores = [3] * len(raw_docs)
        
    # Standardize list size
    if len(relevance_scores) < len(raw_docs):
        relevance_scores += [3] * (len(raw_docs) - len(relevance_scores))
    else:
        relevance_scores = relevance_scores[:len(raw_docs)]
        
    # 3. Filter chunks based on relevance (keep score >= 2)
    filtered_docs = []
    filtered_scores = []
    for doc, score in zip(raw_docs, relevance_scores):
        if score >= 2:
            filtered_docs.append(doc)
            filtered_scores.append(score)
            
    # Safeguard: if all are filtered out, keep the top 2 original similarity chunks
    if not filtered_docs:
        filtered_docs = raw_docs[:2]
        filtered_scores = [3] * len(filtered_docs)
        
    return {
        "retrieved_docs": filtered_docs,
        "relevance_scores": filtered_scores
    }
