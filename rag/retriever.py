"""Query helpers that turn each agent's Chroma collection into an AutoGen tool function."""
import sys
from pathlib import Path

import chromadb

sys.path.append(str(Path(__file__).parent.parent))
from config import AGENTS, CHROMA_DIR

_client = None
_collections = {}


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


def search_reference_book(agent_key: str, query: str, top_k: int = 4) -> str:
    """Run a similarity search against one agent's ingested reference material."""
    collection = _get_collection(agent_key)
    if collection.count() == 0:
        return (
            f"No reference material has been ingested yet for '{agent_key}'. "
            f"Run: python -m rag.ingest --agent {agent_key}"
        )
    results = collection.query(query_texts=[query], n_results=top_k)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return "No relevant passages found in the reference material."

    parts = []
    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown source")
        parts.append(f"[Source: {source}]\n{doc}")
    return "\n\n---\n\n".join(parts)


def make_search_tool(agent_key: str):
    """Return a plain function (with docstring/type hints) AssistantAgent can use as a tool.

    AutoGen AgentChat auto-generates the tool schema from the function signature
    and docstring, so keep both accurate.
    """

    def tool(query: str) -> str:
        f"""Search the {agent_key} reference book for passages relevant to the query.

        Args:
            query: The question or topic to look up in the {agent_key} reference material.

        Returns:
            The most relevant passages found, each tagged with its source document.
        """
        return search_reference_book(agent_key, query)

    tool.__name__ = f"search_{agent_key}_reference_book"
    return tool
