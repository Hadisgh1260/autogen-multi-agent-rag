
"""Interactive console chat with the backend / frontend / manager RAG team.

Run:
    python main.py

Type 'exit' to clear the conversation and start a new session.
Type 'quit' to clear the conversation and close the program.

A session allows a maximum of 3 off-topic questions.
Relevant questions do NOT reset the off-topic counter.
"""

import asyncio
import re

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import HandoffMessage, TextMessage

from agents.team import build_team


MAX_OFF_TOPIC_QUESTIONS = 3
OFF_TOPIC_TAG = "[OFF-TOPIC]"


# -------------------------------------------------------------------
# Local relevance check
# -------------------------------------------------------------------
# Used ONLY after the user has already reached 3 off-topic questions.
# This prevents spending model tokens just to discover that another
# obviously unrelated question should be blocked.
#
# If the question contains one of these terms, we consider it likely
# related to software engineering and allow it to reach the team.
# -------------------------------------------------------------------

RELEVANT_KEYWORDS = {
    # HTTP / API / Web
    "http",
    "https",
    "api",
    "rest",
    "restful",
    "endpoint",
    "request",
    "response",
    "status code",
    "header",
    "cookie",
    "session",
    "cors",
    "webhook",
    "json",
    "xml",

    # Backend
    "backend",
    "server",
    "database",
    "sql",
    "mysql",
    "postgresql",
    "postgres",
    "mongodb",
    "redis",
    "docker",
    "microservice",
    "authentication",
    "authorization",
    "jwt",
    "oauth",
    "fastapi",
    "django",
    "flask",
    "node",
    "nodejs",
    "express",

    # Frontend
    "frontend",
    "front end",
    "html",
    "css",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "nextjs",
    "vue",
    "angular",
    "tailwind",
    "dom",
    "browser",
    "ui",
    "ux",
    "component",
    "responsive",

    # Programming / Engineering
    "python",
    "java",
    "c++",
    "c#",
    "javascript",
    "typescript",
    "code",
    "coding",
    "programming",
    "function",
    "class",
    "variable",
    "algorithm",
    "debug",
    "debugging",
    "error",
    "exception",
    "bug",
    "library",
    "framework",
    "package",
    "module",
    "dependency",
    "git",
    "github",
    "repository",
    "repo",
    "deployment",
    "deploy",
    "devops",
    "ci/cd",
    "linux",
    "terminal",
    "powershell",

    # AI / Agents / RAG
    "ai",
    "artificial intelligence",
    "machine learning",
    "llm",
    "model",
    "agent",
    "multi-agent",
    "autogen",
    "rag",
    "retrieval",
    "embedding",
    "vector",
    "chromadb",
    "groq",
    "openai",
    "prompt",
    "token",

    # General engineering/process questions
    "architecture",
    "software architecture",
    "system design",
    "technical",
    "software",
    "engineering",
    "project",
    "workflow",
    "implementation",
}


def _normalize_text(text: str) -> str:
    """Normalize text for simple keyword matching."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _looks_relevant_locally(text: str) -> bool:
    """
    Return True when the question contains a recognizable
    software-engineering/backend/frontend/AI keyword.

    This is intentionally conservative and is only used after
    the 3 off-topic-question limit has already been reached.
    """
    normalized = _normalize_text(text)

    for keyword in RELEVANT_KEYWORDS:
        if keyword in normalized:
            return True

    return False


# -------------------------------------------------------------------
# AutoGen helpers
# -------------------------------------------------------------------

def _last_agent_before_user(messages) -> str | None:
    """Find the last agent that handed the conversation back to the user."""
    for m in reversed(messages):
        if isinstance(m, HandoffMessage) and m.target == "user":
            return m.source

    return None


def _contains_off_topic(messages) -> bool:
    """Check whether the current turn contains an off-topic response."""
    for m in messages:
        if isinstance(m, TextMessage) and m.source != "user":
            content = str(m.content).strip()

            if OFF_TOPIC_TAG in content:
                return True

    return False


async def run_quiet(team, task) -> TaskResult:
    """
    Run the team while printing only the useful final messages.

    Duplicate [OFF-TOPIC] messages are suppressed.
    """
    result: TaskResult | None = None
    off_topic_printed = False

    async for item in team.run_stream(task=task):

        if isinstance(item, TaskResult):
            result = item

        elif isinstance(item, TextMessage) and item.source != "user":

            content = str(item.content).strip()

            if OFF_TOPIC_TAG in content:

                if not off_topic_printed:
                    print(f"\n{OFF_TOPIC_TAG}\n")
                    off_topic_printed = True

                continue

            print(f"\n{content}\n")

    assert result is not None

    return result


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

async def main():

    team = build_team()

    print(
        "Team ready. Ask a backend, frontend, or manager/process question."
    )

    print(
        "You can ask up to 3 unrelated questions per session."
    )

    print(
        "Type 'exit' to clear the conversation and start a new session."
    )

    print(
        "Type 'quit' to clear the conversation and close the program.\n"
    )

    last_agent: str | None = None

    off_topic_count = 0

    while True:

        text = input("You: ").strip()

        # -----------------------------------------------------------
        # EXIT
        # -----------------------------------------------------------

        if text.lower() == "exit":

            await team.reset()

            last_agent = None
            off_topic_count = 0

            print("\nConversation history cleared.")
            print("Starting a fresh conversation.\n")

            continue

        # -----------------------------------------------------------
        # QUIT
        # -----------------------------------------------------------

        if text.lower() == "quit":

            await team.reset()

            last_agent = None
            off_topic_count = 0

            print("\nConversation history cleared. Goodbye.")

            break

        # -----------------------------------------------------------
        # EMPTY INPUT
        # -----------------------------------------------------------

        if not text:
            continue

        # -----------------------------------------------------------
        # AFTER 3 OFF-TOPIC QUESTIONS
        # -----------------------------------------------------------
        #
        # IMPORTANT:
        # We do NOT block everything here.
        #
        # We first check locally whether the question looks like
        # a software-engineering question.
        #
        # Example:
        #   "what is HTTP 404?" -> allowed
        #
        #   "who is Messi?" -> blocked
        #
        # This local check does not use the LLM.
        # -----------------------------------------------------------

        if off_topic_count >= MAX_OFF_TOPIC_QUESTIONS:

            if not _looks_relevant_locally(text):

                print(
                    "\n[Blocked] You have reached the maximum of "
                    f"{MAX_OFF_TOPIC_QUESTIONS} unrelated questions "
                    "for this session."
                )

                print(
                    "Please ask a backend, frontend, or "
                    "engineering-process question, "
                    "or type 'exit' to start a new session.\n"
                )

                continue

        # -----------------------------------------------------------
        # BUILD TASK
        # -----------------------------------------------------------

        if last_agent is None:

            # First question or previous question was off-topic.
            # Start from manager.
            task = text

        else:

            # Follow-up question goes directly to the agent that
            # answered the previous question.
            task = HandoffMessage(
                source="user",
                target=last_agent,
                content=text,
            )
        
        # -----------------------------------------------------------
        # RUN TEAM
        # -----------------------------------------------------------

        try:

            result = await run_quiet(team, task)

            # -------------------------------------------------------
            # OFF-TOPIC RESULT
            # -------------------------------------------------------

            if _contains_off_topic(result.messages):

                off_topic_count += 1

                print(
                    f"[Off-topic count: "
                    f"{off_topic_count}/{MAX_OFF_TOPIC_QUESTIONS}]\n"
                )

                # Important:
                # Next question must start from manager.
                last_agent = None

            # -------------------------------------------------------
            # RELEVANT RESULT
            # -------------------------------------------------------

            else:

                last_agent = _last_agent_before_user(
                    result.messages
                )

        # -----------------------------------------------------------
        # ERROR
        # -----------------------------------------------------------

        except Exception as e:

            print(
                f"\n[Error] {type(e).__name__}: "
                f"{str(e)[:300]}\n"
            )

            await team.reset()

            last_agent = None

            print(
                "Conversation was reset. "
                "Your next question will start with the manager.\n"
            )


if __name__ == "__main__":
    asyncio.run(main())
