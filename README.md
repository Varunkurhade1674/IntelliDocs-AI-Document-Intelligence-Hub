# IntelliDocs AI – Multi-Agent Document Intelligence Platform (Agentic AI + RAG)

## Overview

IntelliDocs AI is an advanced Multi-Agent Document Intelligence Platform that combines Retrieval-Augmented Generation (RAG), Large Language Models (LLMs), and Agentic AI workflows to enable intelligent document understanding and contextual question answering.

The platform allows users to upload and analyze PDF, DOCX, TXT, and CSV documents, perform semantic search using vector embeddings, and receive verified, citation-backed answers generated through a collaborative multi-agent pipeline orchestrated by LangGraph.

---

## Key Features

### Multi-Agent AI Workflow

The system uses four specialized AI agents:

#### Retrieval Agent

* Retrieves the most relevant document chunks from the FAISS vector database.
* Scores and ranks document relevance.

#### Summarization Agent

* Synthesizes retrieved content.
* Removes redundant information.
* Produces concise context for downstream processing.

#### Fact Verification Agent

* Verifies claims against original document sources.
* Detects unsupported information.
* Reduces hallucinations.

#### Answer Generation Agent

* Generates final responses.
* Incorporates verified context and conversation history.
* Provides source citations.

---

## Architecture

```text
User Query
     │
     ▼
Retrieval Agent
     │
     ▼
Summarization Agent
     │
     ▼
Fact Verification Agent
     │
     ▼
Answer Generation Agent
     │
     ▼
Final Response + Citations
```

---

## Technology Stack

### Frontend

* Streamlit

### Backend

* Python

### Generative AI

* Google Gemini
* OpenAI GPT Models
* Groq Llama Models

### Agent Framework

* LangGraph

### RAG Components

* LangChain
* FAISS Vector Database
* HuggingFace Embeddings

### Database

* SQLite

### Document Processing

* PyMuPDF
* python-docx
* pandas

---

## Supported File Formats

* PDF
* DOCX
* TXT
* CSV

---

## Core Functionalities

### Intelligent Document Search

Perform semantic search across uploaded documents using vector embeddings and similarity matching.

### Context-Aware Question Answering

Ask natural language questions and receive contextual responses grounded in document content.

### Citation-Based Responses

Every answer includes supporting source references and document excerpts.

### Persistent Chat Sessions

Conversation history is stored locally using SQLite for continuity and future reference.

### Multi-Provider LLM Support

Switch between:

* Google Gemini
* OpenAI
* Groq (Llama Models)

---

## Project Structure

```text
IntelliDocs-AI/
│
├── app.py
├── diag.py
├── requirements.txt
├── README.md
├── chats.db
│
├── agents/
│   ├── __init__.py
│   ├── state.py
│   ├── utils.py
│   ├── retrieval_agent.py
│   ├── summarization_agent.py
│   ├── verification_agent.py
│   ├── generation_agent.py
│   └── workflow.py
│
├── vector_store/
│
├── uploads/
│
└── .env
```

---

## Installation

### Clone Repository

```bash
git clone https://github.com/Varunkurhade1674/IntelliDocs-AI-Document-Intelligence-Hub.git

cd IntelliDocs-AI-Document-Intelligence-Hub
```

### Create Virtual Environment

```bash
python -m venv venv
```

### Activate Environment

Windows:

```bash
venv\Scripts\activate
```

Linux / macOS:

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables and API Keys

The system requires API keys for different LLM providers. Create a `.env` file in the root directory and add your keys:

```env
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
```

### How to Get API Keys

#### Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click on **Get API key** and generate a new key.

#### OpenAI API Key
1. Go to the [OpenAI Developer Platform](https://platform.openai.com/).
2. Sign in or create an account.
3. Navigate to **API keys** and click **Create new secret key**.

#### Groq API Key
1. Go to the [Groq Console](https://console.groq.com/).
2. Sign in or create an account.
3. Navigate to **API Keys** and generate a new key.

#### OpenRouter API Key
1. Go to [OpenRouter](https://openrouter.ai/).
2. Sign in or create a free account.
3. Navigate to **Keys** in your dashboard and click **Create Key**.
4. Your key will begin with `sk-or-`.
5. OpenRouter provides access to 100+ models (GPT-4, Claude, Llama, Mistral, etc.) through a single key.

---

## Run Diagnostics

```bash
python diag.py
```

This verifies:

* API connectivity
* Database health
* FAISS index availability
* Document parsing libraries

---

## Launch Application

```bash
streamlit run app.py
```

Application URL:

```text
http://localhost:8501
```

---

## Example Workflow

1. Upload a PDF document.
2. System extracts and indexes content.
3. Embeddings are generated and stored in FAISS.
4. User asks a question.
5. Multi-Agent workflow executes:

   * Retrieval Agent
   * Summarization Agent
   * Verification Agent
   * Generation Agent
6. Verified answer with citations is displayed.

---

## Future Enhancements

* Multi-document comparison
* Knowledge Graph generation
* Voice-based document interaction
* Agent performance analytics
* Enterprise authentication and RBAC
* Cloud deployment support
