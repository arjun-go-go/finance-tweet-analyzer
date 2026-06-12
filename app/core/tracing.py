"""LangSmith tracing setup — must be imported before any LangChain imports."""
import os

from app.core.config import settings

if settings.langsmith_api_key and settings.langsmith_tracing:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
