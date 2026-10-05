"""Query helpers that turn each agent's Chroma collection into an AutoGen tool function."""
import sys
from pathlib import Path

import chromadb

sys.path.append(str(Path(__file__).parent.parent))
from config import AGENTS, CHROMA_DIR

_client = None
_collections = {}

# Keep RAG results small to reduce model input tokens.
DEFAULT_TOP_K = 2
MAX_CHARS_PER_PASSAGE = 1800


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _get_collection(agent_key: str):
    if agent_key not in _collections:
        name = AGENTS[agent_key]["collection"]
        _collections[agent_key] = _get_client().get_or_create_collection(name=name)
    return _collections[agent_key]


def search_reference_book(
    agent_key: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """Search the agent's private reference material.

    Returns only a small number of relevant passages to keep model context compact.
    """
    collection = _get_collection(agent_key)

    if collection.count() == 0:
        return (
            f"No reference material has been ingested yet for '{agent_key}'. "
            f"Run: python -m rag.ingest --agent {agent_key}"
        )

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return "No passages found in the reference material."

    parts = []
    seen_sources = set()

    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown source")

        # Avoid sending duplicate passages from the same source.
        source_key = source.lower().strip()
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        # Limit passage size to control input tokens.
        doc = doc.strip()
        if len(doc) > MAX_CHARS_PER_PASSAGE:
            doc = doc[:MAX_CHARS_PER_PASSAGE].rsplit(" ", 1)[0] + "..."

        parts.append(f"[Source: {source}]\n{doc}")

    return "\n\n---\n\n".join(parts)


def make_search_tool(agent_key: str):
    """Return a search tool for an agent's private reference library."""

    def tool(query: str) -> str:
        return search_reference_book(agent_key, query)

    tool.__doc__ = (
        f"Search the {agent_key} reference library for relevant passages.\n\n"
        f"Args:\n"
        f"    query: The question or topic to look up.\n\n"
        f"Returns:\n"
        f"    Up to two short relevant passages with their source names."
    )

    tool.__name__ = f"search_{agent_key}_reference_book"
    return tool