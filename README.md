# AutoGen RAG Team: Backend + Frontend + Manager

Three agents, each backed by its own **RAG reference library** (PDFs and/or web pages you
give it), coordinated with AutoGen's `Swarm` + explicit handoffs so the **manager always
sees the question first** and either answers it directly or hands it to a specialist:

- **manager** — always speaks first. Answers process/planning/coordination questions
  itself (from its own reference book); hands backend questions to `backend` and
  frontend questions to `frontend`, with no answer of its own.
- **backend** — API/database/server reference material. Answers, then hands back to `user`.
- **frontend** — UI/framework/browser reference material. Answers, then hands back to `user`.

## How it works

```
your PDFs/URLs -> rag/ingest.py -> Chroma vector store (chroma_db/, one collection per agent)
                                          |
                                          v
                agents/team.py -> AssistantAgent per role, each with a
                                  search_<agent>_reference_book tool
                                          |
                                          v
        Swarm: manager (always first) --handoff--> backend or frontend
                                                        |
                                            specialist answers, --handoff--> user (turn ends)
```

This is AutoGen's official **handoff / Swarm pattern**: each agent hands off to the next
by calling a special tool the model picks, rather than an LLM "selector" guessing who
should speak. The manager explicitly decides where each question goes.

Chroma is a local, free vector database — no external account needed, no separate
embedding API key. It stores everything under `chroma_db/` on disk.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then add your OPENAI_API_KEY
```

## 1. Add reference material

Drop PDFs into:
- `data/backend/`
- `data/frontend/`
- `data/manager/`

Or point the ingester at web pages instead of/in addition to PDFs.

## 2. Ingest it (build the vector stores)

```bash
python -m rag.ingest --agent backend
python -m rag.ingest --agent frontend --urls https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide
python -m rag.ingest --agent manager
```

Re-run any time you add more source material — it's safe to re-run (upserts, no dupes).

## 3. Chat with the team

```bash
python main.py
```

Ask a backend question, a frontend question, or a process question. The manager sees it
first, hands off to the right specialist (or answers it itself for process questions),
and whoever answers searches its own reference book before responding.

## Extending

- **Add another agent**: add an entry to `AGENTS` in `config.py`, create a `data/<name>/`
  folder, ingest it, add a `build_specialist("<name>", model_client)` call in
  `agents/team.py`, include it in the `participants` list, and add it to the manager's
  `handoffs` list plus its routing instructions in `build_manager`'s system message.
- **Swap the LLM**: change `AGENT_MODEL` in `.env`, or swap `OpenAIChatCompletionClient`
  in `agents/team.py` for another provider AutoGen supports.
- **Swap embeddings**: Chroma's default embedding function is bundled and free; pass a
  custom `embedding_function=` to `get_or_create_collection(...)` in `rag/ingest.py` and
  `rag/retriever.py` if you want OpenAI or another embedding model instead.
