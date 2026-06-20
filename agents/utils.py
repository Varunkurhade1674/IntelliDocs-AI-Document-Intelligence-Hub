import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

def get_llm(provider: str, model: str, temperature: float):
    """Instantiate and return the appropriate LLM based on the provider, model, and temperature."""
    if provider == "OpenAI":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY in .env file.")
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    
    elif provider == "Google Gemini":
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY or GOOGLE_API_KEY in .env file.")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=api_key)
    
    else: # Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Missing GROQ_API_KEY in .env file.")
        return ChatGroq(model=model, temperature=temperature, groq_api_key=api_key)
