# IntelliDocs AI – Multi-Agent Document Intelligence Platform (Agentic AI + RAG)

A clean, premium document intelligence platform built with **Streamlit**, **LangChain**, and **LangGraph**. It elevates standard RAG pipelines into a stateful, cooperative **Multi-Agent** workflow. Upload local documents (PDF, DOCX, TXT, CSV), build vector indexes locally via FAISS, and query your data while observing individual agents execute in real-time.

---

## 🤖 Multi-Agent Architecture

Queries are processed sequentially by four specialized agents orchestrated via **LangGraph**:

1. **Retrieval Agent**:
   - Performs semantic similarity searches on the FAISS vector database.
   - Evaluates chunk relevance using a consolidated LLM rating prompt (0-5 scale) to filter out low-relevance noise.
2. **Summarization Agent**:
   - Synthesizes retrieved chunks to eliminate duplicate facts and contradictions.
   - Generates a condensed, structured, and redundancy-free context summary.
3. **Fact Verification Agent**:
   - Cross-references the context summary against raw source documents.
   - Detects potential hallucinations or unsupported claims and drafts a validation report.
4. **Answer Generation Agent**:
   - Uses the context summary and fact-checking report to draft the final response.
   - Employs conversational history (memory) for chat continuity.
   - Embeds inline source and page citations (e.g., `[Source: document.pdf, Page: 2]`).

---

## ⚡ Features

- **Multi-Agent Orchestration**: Sequential coordination built with LangGraph.
- **Agent Monitoring**: Streamlit status widget showing exactly which agent is executing, its active status, and intermediate insights in real-time.
- **Multi-Format Document Parsing**: Upload and parse PDF, DOCX, TXT, or CSV files (with automatic OCR for scanned PDFs using Gemini or Groq Vision models).
- **Persistent Chat History**: Session threads are persisted in a local SQLite database (`chats.db`).
- **Flexible Model Selection**: Choose between **Google Gemini**, **Groq (Llama 3)**, or **OpenAI** for query resolution.
- **Modern UI Styles**: Premium light-themed CSS chat layout, with micro-animations and loading states.

---

## File Structure

The project is structured as follows:

* **[app.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/app.py)**: Main Streamlit application, containing the auth cards, layout containers, and the LangGraph execution loop with live progress tracking.
* **[agents/](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/)**: New module containing agent logic:
  * [state.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/state.py): Defines the shared memory (`AgentState`) structure.
  * [utils.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/utils.py): Manages LLM instantiation across OpenAI, Gemini, and Groq.
  * [retrieval_agent.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/retrieval_agent.py): Performs vector searches and LLM-based relevance filtering.
  * [summarization_agent.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/summarization_agent.py): Synthesizes document chunks into a concise summary.
  * [verification_agent.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/verification_agent.py): Factual check to avoid hallucinations.
  * [generation_agent.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/generation_agent.py): Generates citation-rich responses using conversation history.
  * [workflow.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/agents/workflow.py): Compiles the LangGraph StateGraph workflow.
* **[diag.py](file:///v:/AIPROJECTS/IntelliDocs%20AI/diag.py)**: Diagnostic checks for dependencies, databases, and LLM providers.
* **[requirements.txt](file:///v:/AIPROJECTS/IntelliDocs%20AI/requirements.txt)**: Specifies project requirements including `langgraph`.

---

## Setup & Running Locally

### 1. Prerequisites
- **Python 3.9 - 3.11** installed.

### 2. Create & Activate Virtual Environment
```bash
python -m venv venv

# On Windows (PowerShell)
venv\Scripts\Activate.ps1

# On Windows (CMD)
venv\Scripts\activate.bat

# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY="your-gemini-key"
GROQ_API_KEY="your-groq-key"
OPENAI_API_KEY="your-openai-key"
```

### 5. Running Diagnostics (Optional)
To verify if your credentials, models, vector store, and dependencies are working correctly:
```bash
python diag.py
```

### 6. Run the Application
```bash
streamlit run app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.
