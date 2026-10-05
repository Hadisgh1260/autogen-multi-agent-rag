"""Central configuration for the RAG-powered AutoGen team."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)  # .env always wins, even over stray shell/session env vars

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"          # drop source PDFs here, per agent
CHROMA_DIR = ROOT_DIR / "chroma_db"   # persisted vector store lives here

# One Chroma collection per agent. Add more here if you add more agents.
AGENTS = {
    "backend": {
        "collection": "backend_refs",
        "pdf_dir": DATA_DIR / "backend",
        "description": "Backend engineering expert (APIs, databases, servers, architecture).",
    },
    "frontend": {
        "collection": "frontend_refs",
        "pdf_dir": DATA_DIR / "frontend",
        "description": "Frontend engineering expert (UI, frameworks, styling, browser behavior).",
    },
    "manager": {
        "collection": "manager_refs",
        "pdf_dir": DATA_DIR / "manager",
        "description": "Engineering/project manager (process, planning, coordination, prioritization).",
    },
}

# Which LLM backend the agents reason with: "groq" (default) or "openai"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

# Groq exposes an OpenAI-compatible endpoint, so we reuse OpenAIChatCompletionClient
# with a custom base_url instead of needing a separate client library.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Chunking settings for ingestion
CHUNK_SIZE_WORDS = 300
CHUNK_OVERLAP_WORDS = 50