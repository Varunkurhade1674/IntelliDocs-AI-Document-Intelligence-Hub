# IntelliDocs AI — Streamlit PDF Chatbot

A clean, premium document intelligence assistant built with **Streamlit** and **LangChain**. It lets you upload and index local documents (PDF, DOCX, TXT, CSV), store embeddings in a local vector database (FAISS), and ask questions with citation sources.

---

## Features

- **Multi-Format Document Parsing**: Upload PDF, DOCX, TXT, or CSV files to extract text content.
- **Local Vector Indexing**: Creates embeddings using local HuggingFace models (free, run on CPU) or Gemini/OpenAI embedding APIs and stores them locally via FAISS.
- **Flexible Model Selection**: Choose between **Google Gemini**, **Groq (Llama 3)**, or **OpenAI** for query resolution.
- **Persistent Chat History**: Session threads are persisted in a local SQLite database (`chats.db`).
- **Rich Citation Sources**: Inspect exactly which page and text block of your documents were referenced to answer your queries.
- **Modern UI Styles**: Sleek custom CSS styling mimicking a premium, light-themed modern chat interface.

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

### 5. Run the Application
```bash
streamlit run app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.
