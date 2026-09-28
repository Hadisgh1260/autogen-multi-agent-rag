# AutoGen RAG Team: Backend + Frontend + Manager

A multi-agent RAG system built with **Microsoft AutoGen AgentChat**, where a Manager agent coordinates two specialized agents: Backend and Frontend.

Each agent has its own role, tools, and reference collection. The system uses **RAG (Retrieval-Augmented Generation)** to retrieve relevant information from PDFs and web pages before generating answers.

---

## ✨ Features

* 🤖 Multi-agent system built with **Microsoft AutoGen**
* 🧠 Manager agent for routing and coordination
* ⚙️ Specialized Backend agent
* 🎨 Specialized Frontend agent
* 📚 Agent-specific RAG knowledge bases
* 📄 PDF document ingestion
* 🌐 Web page ingestion
* 🔎 Semantic search with embeddings
* 🗄️ ChromaDB vector database
* 🔄 AutoGen Swarm-based agent handoffs
* 🛠️ Tool-based retrieval
* 🔐 Role and reference isolation
* 🔌 Groq and OpenAI-compatible API support

---

## 🧩 Agents

The system contains three agents:

| Agent       | Responsibility                         | Knowledge Base   |
| ----------- | -------------------------------------- | ---------------- |
| 🧠 Manager  | Understands the question and routes it | `data/manager/`  |
| ⚙️ Backend  | APIs, databases, servers, architecture | `data/backend/`  |
| 🎨 Frontend | UI, JavaScript, CSS, browser behavior  | `data/frontend/` |

### Manager

The Manager agent receives the user's question first.

It can:

* Answer process or planning questions
* Decide which specialist is relevant
* Handoff the task to Backend or Frontend
* Coordinate the conversation between agents

### Backend

The Backend agent focuses on topics such as:

* REST APIs
* Databases
* Authentication
* Servers
* Backend architecture
* Performance
* Python backend development
* API design

### Frontend

The Frontend agent focuses on:

* HTML
* CSS
* JavaScript
* UI development
* Browser behavior
* Client-side performance
* Frontend architecture

---

## 🧠 RAG Architecture

Each specialist agent has its own reference collection.

```text
                         User
                           │
                           ▼
                    ┌─────────────┐
                    │   Manager   │
                    └──────┬──────┘
                           │
                  ┌────────┴────────┐
                  │                 │
                  ▼                 ▼
          ┌──────────────┐  ┌──────────────┐
          │   Backend    │  │   Frontend   │
          └──────┬───────┘  └──────┬───────┘
                 │                 │
                 ▼                 ▼
          Backend RAG        Frontend RAG
                 │                 │
                 ▼                 ▼
          Backend Docs       Frontend Docs
```

The RAG pipeline is:

```text
Documents
   │
   ▼
Chunking
   │
   ▼
Embeddings
   │
   ▼
ChromaDB
   │
   ▼
Semantic Retrieval
   │
   ▼
Relevant Context
   │
   ▼
Agent
   │
   ▼
Answer
```

---

## 📚 Reference Collections

Reference documents are organized by agent:

```text
data/
├── manager/
├── backend/
└── frontend/
```

Each agent retrieves information only from its own configured collection and retrieval tools.

For example:

```text
Backend Agent
     │
     ▼
Backend Retrieval Tool
     │
     ▼
Backend Collection
```

and:

```text
Frontend Agent
     │
     ▼
Frontend Retrieval Tool
     │
     ▼
Frontend Collection
```

---

## 🔐 Role & Reference Isolation

Each agent has a predefined role, dedicated tools, and a separate reference collection.

For example, asking the Frontend agent:

> "Answer this as a Backend engineer."

does not automatically give the Frontend agent access to the Backend agent's tools or reference collection.

---

## 🗂️ Project Structure

```text
autogen-multi-agent-rag/
│
├── agents/
│   ├── __init__.py
│   └── team.py
│
├── rag/
│   ├── __init__.py
│   ├── ingest.py
│   └── retriever.py
│
├── data/
│   ├── manager/
│   ├── backend/
│   └── frontend/
│
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

> The `data/` directory contains local reference documents and is excluded from Git.

---

## ⚙️ Requirements

* Python 3.10+
* Microsoft AutoGen AgentChat 0.7+
* ChromaDB
* Embedding model
* Groq or OpenAI-compatible API

Install the dependencies:

```bash
pip install -r requirements.txt
```

---

## 🔑 Environment Variables

Create a `.env` file based on `.env.example`.

Example:

```env
LLM_PROVIDER=groq

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
```

For OpenAI-compatible providers, configure the corresponding API settings in your environment.

### Important

Never commit your real `.env` file.

The `.gitignore` file excludes it automatically.

---

## 📥 Adding Reference Documents

Place reference documents inside the appropriate agent directory.

For example:

```text
data/
├── backend/
│   ├── backend_book_1.pdf
│   └── backend_book_2.pdf
│
├── frontend/
│   ├── frontend_book_1.pdf
│   └── frontend_book_2.pdf
│
└── manager/
    └── management_reference.pdf
```

The current Git configuration intentionally ignores the entire `data/` directory.

This prevents reference books and other local documents from being accidentally uploaded to GitHub.

---

## 🔎 Building the Knowledge Base

After adding documents, run the ingestion process:

```bash
python rag/ingest.py
```

The ingestion pipeline:

1. Loads documents
2. Extracts text
3. Splits text into chunks
4. Generates embeddings
5. Stores the vectors in ChromaDB

---

## 🌐 Web References

The RAG pipeline can also work with web-page content.

A web page can be processed and added to the appropriate knowledge collection.

The retrieved content is then provided to the relevant specialist agent as context.

---

## 🚀 Running the Project

Start the application with:

```bash
python main.py
```

The user interacts with the Manager agent first.

The Manager decides whether the question should be handled directly or handed off to a specialist.

---

## 💬 Example Questions

### Backend

```text
How should I design a REST API for a large application?
```

```text
What database structure would work for this system?
```

### Frontend

```text
How should I structure the frontend for this application?
```

```text
Why is my JavaScript code causing slow browser performance?
```

### Manager

```text
Which agent should handle authentication?
```

```text
How should we divide the backend and frontend responsibilities?
```

---

## 🔄 Agent Routing

The system uses the **AutoGen Swarm** pattern for agent handoffs.

A simplified flow:

```text
User
 │
 ▼
Manager
 │
 ├──────────────► Backend
 │
 └──────────────► Frontend
```

The Manager analyzes the user's request and determines which specialist should handle it.

Specialists can use their dedicated retrieval tools to access relevant reference material.

---

## 🛠️ Technologies

| Technology             | Purpose                   |
| ---------------------- | ------------------------- |
| Microsoft AutoGen      | Multi-agent orchestration |
| AutoGen AgentChat      | Agent implementation      |
| AutoGen Swarm          | Agent handoffs            |
| ChromaDB               | Vector database           |
| Embeddings             | Semantic retrieval        |
| Python                 | Core implementation       |
| Groq                   | LLM provider              |
| OpenAI-compatible APIs | Alternative LLM providers |

---

## ➕ Adding Another Agent

A new specialist can be added by:

1. Creating a new agent configuration
2. Defining its role and system prompt
3. Creating a dedicated reference directory
4. Creating its retrieval tools
5. Adding a separate ChromaDB collection
6. Updating the Manager's routing logic

For example:

```text
data/
├── manager/
├── backend/
├── frontend/
└── security/
```

The new Security agent could specialize in:

* Authentication
* Authorization
* OWASP
* Secure API design
* Application security

---

## 📖 Supported Reference Types

The RAG pipeline is designed to work with reference materials such as:

* PDF books
* Documentation
* Technical guides
* Web pages
* Other text-based technical references

---

## 🐛 Troubleshooting

### No relevant information is retrieved

Check:

* Documents were added to the correct `data/` directory
* The ingestion process was executed
* The correct collection is being queried
* ChromaDB was created successfully

### API errors

Check:

* `.env` exists
* API key is correct
* Selected model is available
* Provider configuration is correct

### Agent uses general knowledge instead of references

RAG provides retrieved context to the model, but the underlying LLM can still use its general knowledge.

For reference-heavy answers, the agent prompts should encourage grounding answers in retrieved context.

---

## ⚠️ Limitations

* RAG retrieval quality depends on document quality and chunking.
* LLM responses may still contain incorrect information.
* Agent role separation is application-level rather than a security boundary.
* Large document collections may require better indexing and retrieval strategies.
* API availability depends on the selected LLM provider.

---

## 🔒 Security

Do not commit:

```text
.env
API keys
Passwords
Private credentials
Sensitive documents
```

The included `.gitignore` excludes:

```text
.env
data/
chroma_db/
```

Reference documents remain local unless intentionally added to the repository.

---

## 📌 Version

### v1.0.0 — Initial RAG Multi-Agent System

This is the first version of the project.

Included:

* Manager, Backend, and Frontend agents
* Agent-specific RAG collections
* PDF and web-page ingestion
* AutoGen Swarm routing
* Tool-based handoffs
* Role and reference isolation
* Groq / OpenAI-compatible LLM support


Built with:

**Python · Microsoft AutoGen · RAG · ChromaDB · Groq**
