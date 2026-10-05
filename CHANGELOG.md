# Changelog

All notable changes to this project are documented in this file.

---

## [v2.0.0] - 2026-10-05

### Added

- FastAPI backend for the web application
- Browser-based chat interface
- User authentication
- SQLite-based user management
- Secure password hashing with PBKDF2-HMAC-SHA256
- User sessions
- Context-aware follow-up questions
- Personalized user greetings
- Off-topic question tracking
- Temporary blocking after repeated off-topic questions
- Responsive frontend interface
- Enter-to-send and Shift+Enter support

### Improved

- Manager routing and coordination
- Context handling between user messages
- Agent understanding of names and pronouns
- Conversation continuity
- Web-based user experience
- Frontend chat interface

### Maintained

- Manager agent
- Backend agent
- Frontend agent
- AutoGen Swarm
- RAG pipeline
- ChromaDB
- Agent-specific knowledge collections
- PDF and web-page ingestion
- Groq / OpenAI-compatible model support

---

## [v1.0.0] - Initial Release

### Added

- Initial multi-agent RAG system
- Manager agent
- Backend agent
- Frontend agent
- Agent-specific RAG collections
- PDF document ingestion
- Web-page ingestion
- ChromaDB vector database
- Semantic retrieval
- AutoGen Swarm routing
- Tool-based retrieval
- Role and reference isolation
- Groq / OpenAI-compatible API support

---

## Versioning

This project follows semantic versioning:

```text
MAJOR.MINOR.PATCH
