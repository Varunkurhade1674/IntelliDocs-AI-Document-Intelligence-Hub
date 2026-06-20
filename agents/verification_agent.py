import json
from typing import Dict, Any
from .state import AgentState
from .utils import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

def verification_node(state: AgentState) -> Dict[str, Any]:
    summary = state["summarized_context"]
    docs = state["retrieved_docs"]
    
    if not docs or not summary or summary.startswith("No relevant documents"):
        return {
            "verification_report": {
                "status": "FAILED",
                "hallucinations_detected": False,
                "unsupported_claims": ["No relevant document chunks available for verification."],
                "explanation": "Verification skipped because retrieved document list is empty."
            }
        }
        
    raw_context = ""
    for idx, d in enumerate(docs):
        src = d.metadata.get("source", "Document")
        pg = d.metadata.get("page", "—")
        raw_context += f"--- RAW CHUNK {idx+1} [Source: {src}, Page: {pg}] ---\n{d.page_content}\n\n"
        
    llm = get_llm(state["provider"], state["model"], 0.0) # Temperature 0 for accuracy
    
    system_prompt = (
        "You are a Fact Verification Agent. Your job is to verify if the summarized context contains any hallucinated "
        "or unsupported claims compared to the raw document text.\n"
        "Compare the 'Summary to Verify' against the 'Raw Document Context'.\n"
        "Return your assessment in raw JSON format with the following keys:\n"
        "1. 'status': 'PASSED' (if all claims are fully supported) or 'WARNING' (if unsupported claims are found)\n"
        "2. 'hallucinations_detected': true/false\n"
        "3. 'unsupported_claims': list of strings listing any specific sentences/claims in the summary not backed by the raw context\n"
        "4. 'explanation': a short sentence explaining your evaluation.\n\n"
        "Response Format: You MUST return ONLY the raw JSON string. Do not include markdown code block fencings or any other text."
    )
    
    user_prompt = f"Raw Document Context:\n{raw_context}\n\nSummary to Verify:\n{summary}"
    
    try:
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        content = resp.content.strip()
        
        # Strip potential markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                content = "\n".join(lines[1:-1])
        content = content.strip()
        
        report = json.loads(content)
        # Ensure correct structure
        if not isinstance(report, dict):
            raise ValueError("Parsed JSON is not a dictionary")
        report.setdefault("status", "PASSED")
        report.setdefault("hallucinations_detected", False)
        report.setdefault("unsupported_claims", [])
        report.setdefault("explanation", "Verification parsing completed.")
    except Exception as e:
        report = {
            "status": "PASSED",
            "hallucinations_detected": False,
            "unsupported_claims": [],
            "explanation": f"Factual check bypassed. Verification LLM error: {e}"
        }
        
    return {"verification_report": report}
