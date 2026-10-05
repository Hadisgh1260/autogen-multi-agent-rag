# AutoGen RAG Team

A multi-agent RAG web application built with **Microsoft AutoGen AgentChat**, where a Manager agent coordinates specialized Backend and Frontend agents.

The project started as a console-based RAG system and evolved into a web application with authentication, session management, contextual follow-ups, and an English chat interface.

---

## ✨ Features

### Multi-Agent RAG

- 🤖 Microsoft AutoGen AgentChat
- 🧠 Manager agent for routing and coordination
- ⚙️ Specialized Backend agent
- 🎨 Specialized Frontend agent
- 📚 Agent-specific RAG knowledge bases
- 🔎 Semantic search with embeddings
- 🗄️ ChromaDB vector database
- 🔄 AutoGen Swarm-based agent handoffs
- 🛠️ Tool-based retrieval
- 🔐 Role and reference isolation

### Web Application

- 🌐 FastAPI backend
- 💬 Browser-based chat interface
- 🔐 User authentication
- 🗃️ SQLite user database
- 🔑 Secure password hashing
- 👤 User sessions
- 🧠 Context-aware follow-up questions
- 🚫 Off-topic question protection
- ⏱️ Temporary blocking after repeated off-topic questions
- 📱 Responsive web interface
- ⌨️ Enter-to-send and Shift+Enter for new lines

### RAG Sources

- 📄 PDF documents
- 🌐 Web pages
- 📖 Technical documentation
- 📚 Agent-specific reference materials

---

## 🏗️ Architecture

The application contains three AI agents:

| Agent | Responsibility | Knowledge Base |
|---|---|---|
| 🧠 Manager | Understands requests, coordinates the team, and routes questions | `data/manager/` |
| ⚙️ Backend | APIs, databases, servers, authentication, and backend architecture | `data/backend/` |
| 🎨 Frontend | HTML, CSS, JavaScript, UI, browser behavior, and frontend architecture | `data/frontend/` |

### Agent Flow

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

The Manager receives the user's request first and determines whether it should:

1. Answer directly
2. Route the request to Backend
3. Route the request to Frontend

---

## 🧠 RAG Architecture

Each specialist agent has its own retrieval tool and reference collection.

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
Specialist Agent
    │
    ▼
Answer
```

Reference materials are separated by agent:

```text
data/
├── manager/
├── backend/
└── frontend/
```

Each agent retrieves information only from its configured collection.

---

## 🌐 Web Application

Version 2 introduces a browser-based interface on top of the original multi-agent RAG system.

The application consists of:

```text
Browser
   │
   ▼
Frontend
   │
   ▼
FastAPI Backend
   │
   ▼
AutoGen Swarm
   │
   ├── Manager
   ├── Backend
   └── Frontend
        │
        ▼
       RAG
        │
        ▼
    ChromaDB
```

---

## 🔐 Authentication

The web application includes a local authentication system using SQLite.

User accounts contain:

- Username
- Password hash
- Password salt
- Off-topic question count
- Temporary block information
- Account creation timestamp

Passwords are not stored as plain text.

Password hashing uses:

```text
PBKDF2-HMAC-SHA256
```

with a randomly generated salt.

The SQLite database is local and is intentionally excluded from Git.

---

## 🚫 Off-Topic Protection

The application is designed for:

- Backend questions
- Frontend questions
- Software engineering questions
- Related technical discussions

Repeated unrelated questions are tracked per user session.

The current configuration allows:

```text
Maximum off-topic questions: 3
Temporary block duration: 24 hours
```

After reaching the limit, the user is temporarily blocked from asking further questions.

---

## 📁 Project Structure

```text
autogen-multi-agent-rag/
│
├── agents/
│   ├── __init__.py
│   └── team.py
│
├── backend/
│   ├── __init__.py
│   ├── create_user.py
│   └── main.py
│
├── frontend/
│   ├── app.js
│   ├── chat.html
│   ├── index.html
│   └── style.css
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
├── README.md
└── CHANGELOG.md
```

### Important Local Files

The following files are intentionally kept local and are not committed:

```text
.env
users.db
chroma_db/
data/
```

---

## ⚙️ Requirements

- Python 3.10+
- Microsoft AutoGen AgentChat
- AutoGen OpenAI-compatible model client
- FastAPI
- Uvicorn
- ChromaDB
- Embedding model
- Groq or another OpenAI-compatible API provider

Install dependencies with:

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
## 📚 Adding Reference Documents

Place reference documents inside the appropriate agent directory.

Example:

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


--

## 🔎 Building the Knowledge Base

After adding reference documents, run:

```bash
python rag/ingest.py
```

The ingestion pipeline:

1. Loads documents
2. Extracts text
3. Splits text into chunks
4. Generates embeddings
5. Stores vectors in ChromaDB

The resulting ChromaDB data is stored locally.

---

## 🌐 Web Page References

The RAG system can also process web-page content.

Web content can be added to the appropriate agent knowledge collection and later retrieved as contextual information during conversations.

---

## 🚀 Running the Application

### Web Application

Start the FastAPI server with:

```bash
uvicorn backend.main:app --reload
```

Then open the application in your browser.

The web application provides:

- Login
- User sessions
- Chat
- Agent routing
- Context-aware conversations
- Off-topic protection

---

### Console Application

The original console interface is still available:

```bash
python main.py
```

This provides direct interaction with the AutoGen team without the web interface.

---

## 👤 Creating a User

A helper script is included for creating local users:

```bash
python backend/create_user.py
```

The user information is stored in the local SQLite database:

```text
users.db
```

This file is ignored by Git.


---

## 🔄 Agent Routing

The project uses the **AutoGen Swarm** pattern for agent handoffs.

Simplified routing:

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

The Manager determines which specialist is relevant.

Specialist agents can then use their dedicated retrieval tools to access their reference material.

---

## 🛠️ Technologies

| Technology | Purpose |
|---|---|
| Python | Core implementation |
| Microsoft AutoGen | Multi-agent orchestration |
| AutoGen AgentChat | Agent implementation |
| AutoGen Swarm | Agent handoffs |
| FastAPI | Web backend |
| Uvicorn | ASGI server |
| HTML / CSS / JavaScript | Web interface |
| SQLite | User management |
| ChromaDB | Vector database |
| Embeddings | Semantic retrieval |
| Groq | LLM provider |
| OpenAI-compatible APIs | Model provider compatibility |

---

## ➕ Adding Another Agent

A new specialist can be added by:

1. Creating a new agent configuration
2. Defining its role and system prompt
3. Creating a dedicated reference directory
4. Creating its retrieval tools
5. Adding a separate ChromaDB collection
6. Updating the Manager's routing logic

---

## 📖 Supported Reference Types

The RAG pipeline is designed to work with reference materials such as:

- PDF books
- Technical documentation
- Technical guides
- Web pages
- Other text-based technical references

---


## ⚠️ Limitations

- RAG quality depends on the quality of the reference documents.
- Chunking and embedding configuration affect retrieval quality.
- LLM responses may still contain incorrect information.
- Agent role separation is primarily an application-level design.
- Large knowledge bases may require more advanced retrieval strategies.
- API availability depends on the selected LLM provider.
- User sessions are currently maintained in application memory.

---

## 📌 Current Version

### v2.0.0 — Web Application

Version 2 evolves the original RAG system into a web-based multi-agent application.

#### Added

- FastAPI backend
- Browser-based chat interface
- User authentication
- SQLite user management
- Password hashing
- User sessions
- Context-aware follow-up handling
- Off-topic question tracking
- Temporary user blocking
- Personalized user greetings
- Responsive web interface

#### Improved

- Manager routing
- Agent context handling
- Conversation continuity
- User experience
- Frontend interface

#### Maintained

- Manager agent
- Backend agent
- Frontend agent
- RAG pipeline
- ChromaDB
- AutoGen Swarm
- Agent-specific knowledge collections

---

## 📜 Version History

### v1.0.0 — Initial RAG Multi-Agent System

The original release introduced:

- Manager, Backend, and Frontend agents
- Agent-specific RAG collections
- PDF and web-page ingestion
- AutoGen Swarm routing
- Tool-based retrieval
- Role and reference isolation
- Groq / OpenAI-compatible LLM support

For detailed version history, see:

```text
CHANGELOG.md
```

Built with:

**Python · Microsoft AutoGen · FastAPI · RAG · ChromaDB · SQLite · Groq**
