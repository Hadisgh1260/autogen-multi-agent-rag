import asyncio
import hashlib
import hmac
import os
import secrets
import sqlite3

import requests

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import HandoffMessage, TextMessage

from agents.team import build_team


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "users.db"
FRONTEND_DIR = BASE_DIR / "frontend"


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(BASE_DIR / ".env")

TURNSTILE_SECRET_KEY = os.getenv(
    "TURNSTILE_SECRET_KEY"
)


# ============================================================
# SETTINGS
# ============================================================

MAX_OFF_TOPIC = 3
BLOCK_HOURS = 24
OFF_TOPIC_TAG = "[OFF-TOPIC]"


# ============================================================
# CLOUDFLARE TURNSTILE
# ============================================================

TURNSTILE_VERIFY_URL = (
    "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)


def verify_turnstile(
    token: str,
) -> bool:

    if not TURNSTILE_SECRET_KEY:

        raise RuntimeError(
            "TURNSTILE_SECRET_KEY is not configured."
        )

    response = requests.post(
        TURNSTILE_VERIFY_URL,
        data={
            "secret": TURNSTILE_SECRET_KEY,
            "response": token,
        },
        timeout=10,
    )

    response.raise_for_status()

    result = response.json()

    return bool(
        result.get("success", False)
    )


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="AutoGen RAG Team",
    version="1.0.0",
)


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():

    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            off_topic_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated "
        "ON chat_sessions(user_id, updated_at DESC)"
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session "
        "ON chat_messages(session_id, id ASC)"
    )

    conn.commit()
    conn.close()


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(
    password: str,
    salt: Optional[str] = None,
):

    if salt is None:
        salt = secrets.token_hex(16)

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()

    return hashed, salt


def verify_password(
    password: str,
    stored_hash: str,
    stored_salt: str,
):

    calculated_hash, _ = hash_password(
        password,
        stored_salt,
    )

    return hmac.compare_digest(
        calculated_hash,
        stored_hash,
    )


# ============================================================
# USER HELPERS
# ============================================================

def get_user(username: str):

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()

    conn.close()

    return user


def get_user_by_id(user_id: int):

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()

    conn.close()

    return user


def update_off_topic_count(
    user_id: int,
    count: int,
    blocked_until: Optional[str],
):

    conn = get_db()

    conn.execute(
        """
        UPDATE users
        SET off_topic_count = ?,
            blocked_until = ?
        WHERE id = ?
        """,
        (
            count,
            blocked_until,
            user_id,
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# CHAT HISTORY HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_chat_session(
    user_id: int,
    title: str = "New chat",
):

    timestamp = now_iso()

    conn = get_db()

    cursor = conn.execute(
        """
        INSERT INTO chat_sessions (
            user_id, title, created_at, updated_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            timestamp,
            timestamp,
        ),
    )

    chat_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return int(chat_id)


def get_chat_session(
    chat_id: int,
    user_id: int,
):

    conn = get_db()

    chat = conn.execute(
        """
        SELECT *
        FROM chat_sessions
        WHERE id = ? AND user_id = ?
        """,
        (chat_id, user_id),
    ).fetchone()

    conn.close()

    return chat


def get_chat_sessions(user_id: int):

    conn = get_db()

    chats = conn.execute(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM chat_sessions
        WHERE user_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    return chats


def get_chat_messages(
    chat_id: int,
):

    conn = get_db()

    messages = conn.execute(
        """
        SELECT id, session_id, role, content, created_at
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    ).fetchall()

    conn.close()

    return messages


def add_chat_message(
    chat_id: int,
    role: str,
    content: str,
):

    timestamp = now_iso()

    conn = get_db()

    conn.execute(
        """
        INSERT INTO chat_messages (
            session_id, role, content, created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            chat_id,
            role,
            content,
            timestamp,
        ),
    )

    conn.execute(
        """
        UPDATE chat_sessions
        SET updated_at = ?
        WHERE id = ?
        """,
        (timestamp, chat_id),
    )

    conn.commit()
    conn.close()


def make_chat_title(question: str):

    title = " ".join(
        question.strip().split()
    )

    if not title:
        return "New chat"

    if len(title) <= 48:
        return title

    return title[:48].rstrip() + "..."


def set_chat_title_if_new(
    chat_id: int,
    question: str,
):

    conn = get_db()

    chat = conn.execute(
        """
        SELECT title
        FROM chat_sessions
        WHERE id = ?
        """,
        (chat_id,),
    ).fetchone()

    if chat and chat["title"] == "New chat":

        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                make_chat_title(question),
                now_iso(),
                chat_id,
            ),
        )

        conn.commit()

    conn.close()


def delete_chat_session(
    chat_id: int,
    user_id: int,
):

    conn = get_db()

    cursor = conn.execute(
        """
        DELETE FROM chat_sessions
        WHERE id = ? AND user_id = ?
        """,
        (chat_id, user_id),
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# SESSIONS
# ============================================================

sessions = {}


def create_session(user_id: int):

    token = secrets.token_urlsafe(32)

    sessions[token] = {
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
    }

    return token


def get_current_user(
    authorization: Optional[str],
):

    if not authorization:

        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    if not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header.",
        )

    token = authorization[7:]

    session = sessions.get(token)

    if session is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session.",
        )

    user = get_user_by_id(
        session["user_id"]
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="User not found.",
        )

    return user


# ============================================================
# BLOCK STATUS
# ============================================================

def is_user_blocked(user):

    blocked_until = user["blocked_until"]

    if not blocked_until:
        return False

    blocked_time = datetime.fromisoformat(
        blocked_until
    )

    now = datetime.now(timezone.utc)

    if now < blocked_time:
        return True

    update_off_topic_count(
        user["id"],
        0,
        None,
    )

    return False


def remaining_block_time(user):

    blocked_until = user["blocked_until"]

    if not blocked_until:
        return 0

    blocked_time = datetime.fromisoformat(
        blocked_until
    )

    now = datetime.now(timezone.utc)

    seconds = int(
        (blocked_time - now).total_seconds()
    )

    return max(seconds, 0)


# ============================================================
# AUTO-GEN TEAM STORAGE
# ============================================================

# One Swarm per user + chat.
# This keeps AutoGen context isolated between conversations.

user_teams = {}
team_locks = {}

# The specialist that produced the previous completed answer.
last_agents = {}

# Last answer is stored separately so that if the AutoGen context
# becomes invalid/too large, we can rebuild the immediate context.
last_answers = {}


def chat_team_key(user_id: int, chat_id: int):
    return (user_id, chat_id)


def get_team(
    user_id: int,
    chat_id: int,
):

    key = chat_team_key(
        user_id,
        chat_id,
    )

    if key not in user_teams:
        user_teams[key] = build_team()

    if key not in team_locks:
        team_locks[key] = asyncio.Lock()

    return user_teams[key]


async def reset_chat_team(
    user_id: int,
    chat_id: int,
):

    key = chat_team_key(
        user_id,
        chat_id,
    )

    team = user_teams.get(key)

    if team is not None:

        try:
            await team.reset()
        except Exception:
            pass

    user_teams.pop(key, None)
    team_locks.pop(key, None)
    last_agents.pop(key, None)
    last_answers.pop(key, None)


async def reset_user_teams(user_id: int):

    keys = [
        key
        for key in user_teams
        if key[0] == user_id
    ]

    for key in keys:
        await reset_chat_team(
            key[0],
            key[1],
        )


# ============================================================
# FOLLOW-UP DETECTION
# ============================================================

def is_follow_up(text: str) -> bool:

    """
    Detect short follow-up messages that clearly refer to the
    previous answer.

    New questions are NOT treated as follow-ups just because
    the same specialist answered the previous question.
    """

    normalized = " ".join(
        text.lower().strip().split()
    )

    if not normalized:
        return False

    # Very short direct confirmations / requests.
    exact_follow_ups = {
        "yes",
        "yeah",
        "yep",
        "sure",
        "okay",
        "ok",
        "please",
        "why",
        "why?",
        "how",
        "how?",
        "more",
        "more detail",
        "more details",
        "tell me more",
        "explain more",
        "go deeper",
        "an example",
        "example",
        "give me an example",
        "show me an example",
        "another example",
        "one more example",
        "can you give me an example?",
        "can you show me an example?",
        "can you explain more?",
    }

    if normalized in exact_follow_ups:
        return True

    # Phrases that explicitly refer to the previous answer.
    follow_up_starts = (
        "give me an example",
        "show me an example",
        "give another example",
        "show another example",
        "give me another example",
        "can you give me an example",
        "can you show me an example",
        "can you explain more",
        "could you explain more",
        "tell me more about that",
        "tell me more about it",
        "explain that more",
        "explain it more",
        "how can i handle it",
        "how do i handle it",
        "how can i fix it",
        "how do i fix it",
        "why does that happen",
        "why is that",
        "why does it",
        "what does that mean",
        "what about that",
        "what about it",
        "can you clarify that",
        "can you clarify it",
        "can you elaborate",
        "could you elaborate",
    )

    if normalized.startswith(follow_up_starts):
        return True

    # Very short questions containing an explicit reference
    # to the previous answer.
    reference_words = (
        "that",
        "it",
        "this",
        "the above",
        "the previous",
    )

    words = normalized.split()

    if len(words) <= 7:

        if any(
            normalized.startswith(
                prefix
            )
            for prefix in (
                "why is that",
                "why does that",
                "how does that",
                "how can that",
                "what about that",
                "what about it",
                "can you explain that",
                "can you explain it",
            )
        ):

            return True

        if (
            words
            and words[0]
            in {
                "yes",
                "yeah",
                "yep",
                "sure",
                "okay",
                "ok",
            }
        ):

            return True

        if any(
            word in normalized
            for word in reference_words
        ):

            if normalized.startswith(
                (
                    "why ",
                    "how ",
                    "what ",
                    "can you ",
                    "could you ",
                )
            ):

                return True

    return False


# ============================================================
# AUTOGEN TASK HELPERS
# ============================================================

def make_task(
    question: str,
    target: str,
):

    return HandoffMessage(
        source="user",
        target=target,
        content=question,
    )


def build_recovery_question(
    question: str,
    previous_answer: Optional[str],
):

    if not previous_answer:
        return question

    return (
        "Continue the user's conversation naturally.\n\n"
        f"Previous assistant answer:\n"
        f"{previous_answer}\n\n"
        f"New user question:\n"
        f"{question}\n\n"
        "Answer the new question directly. "
        "Do not repeat the previous answer unless it is "
        "necessary to answer the new question."
    )


# ============================================================
# RUN AUTOGEN
# ============================================================

async def run_team(
    team,
    task,
    state_key,
):

    result = None
    answer = None
    off_topic = False
    detected_last_agent = None

    async for item in team.run_stream(
        task=task
    ):

        # ----------------------------------------------------
        # FINAL TASK RESULT
        # ----------------------------------------------------

        if isinstance(
            item,
            TaskResult,
        ):

            result = item

            continue

        # ----------------------------------------------------
        # HANDOFF
        # ----------------------------------------------------

        if isinstance(
            item,
            HandoffMessage,
        ):

            if (
                item.target == "user"
                and item.source != "user"
            ):

                detected_last_agent = item.source

            continue

        # ----------------------------------------------------
        # TEXT MESSAGE
        # ----------------------------------------------------

        if isinstance(
            item,
            TextMessage,
        ):

            if item.source == "user":
                continue

            content = str(
                item.content
            ).strip()

            if not content:
                continue

            # ------------------------------------------------
            # OFF TOPIC
            # ------------------------------------------------

            if OFF_TOPIC_TAG in content:

                off_topic = True
                answer = OFF_TOPIC_TAG

                continue

            # ------------------------------------------------
            # NORMAL ANSWER
            # ------------------------------------------------

            answer = content

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if result is None:

        raise RuntimeError(
            "AutoGen did not return a TaskResult."
        )

    # --------------------------------------------------------
    # SAVE LAST AGENT
    # --------------------------------------------------------

    if detected_last_agent:

        last_agents[state_key] = (
            detected_last_agent
        )

    # --------------------------------------------------------
    # SAVE LAST ANSWER
    # --------------------------------------------------------

    if answer:

        last_answers[state_key] = answer

    return (
        result,
        answer or "No response.",
        off_topic,
        detected_last_agent,
    )


# ============================================================
# RUN ONE CHAT TURN
# ============================================================

async def run_chat_turn(
    user_id: int,
    chat_id: int,
    question: str,
):

    state_key = chat_team_key(
        user_id,
        chat_id,
    )

    team = get_team(
        user_id,
        chat_id,
    )

    lock = team_locks[state_key]

    async with lock:

        previous_agent = last_agents.get(
            state_key
        )

        previous_answer = last_answers.get(
            state_key
        )

        # ----------------------------------------------------
        # ROUTING
        # ----------------------------------------------------
        #
        # A new question always starts with the manager.
        #
        # Only a clear follow-up continues directly with the
        # previous agent.
        #
        # Example:
        #
        # Q1 -> What is an API endpoint?
        #      -> manager -> backend
        #
        # Q2 -> What is a CSS preprocessor?
        #      -> manager -> frontend
        #
        # Q3 -> Can you give me an example?
        #      -> frontend
        # ----------------------------------------------------

        if (
            previous_agent
            and is_follow_up(question)
        ):

            target = previous_agent

        else:

            target = "manager"

        task = make_task(
            question,
            target,
        )

        try:

            return await run_team(
                team,
                task,
                state_key,
            )

        except Exception as first_error:

            # ------------------------------------------------
            # RECOVERY
            # ------------------------------------------------
            #
            # If the persistent Swarm has become invalid or
            # the accumulated context is too large, start a
            # fresh team and retry the current question.
            # ------------------------------------------------

            await reset_chat_team(
                user_id,
                chat_id,
            )

            retry_team = get_team(
                user_id,
                chat_id,
            )

            recovery_question = (
                build_recovery_question(
                    question,
                    previous_answer,
                )
            )

            retry_task = make_task(
                recovery_question,
                "manager",
            )

            try:

                return await run_team(
                    retry_team,
                    retry_task,
                    state_key,
                )

            except Exception as second_error:

                raise RuntimeError(
                    "AutoGen failed after retry. "
                    f"First error: "
                    f"{str(first_error)[:200]} | "
                    f"Retry error: "
                    f"{str(second_error)[:300]}"
                ) from second_error


# ============================================================
# SIMPLE LOCAL RELEVANCE CHECK
# ============================================================

RELEVANT_KEYWORDS = {

    # HTTP / API
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

    # Programming
    "python",
    "java",
    "c++",
    "c#",
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
    "linux",
    "powershell",
    "terminal",

    # AI / RAG
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

    # Engineering
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


def looks_relevant(text: str):

    normalized = text.lower().strip()

    return any(
        keyword in normalized
        for keyword in RELEVANT_KEYWORDS
    )


# ============================================================
# REQUEST MODELS
# ============================================================

class LoginRequest(BaseModel):

    username: str
    password: str
    turnstile_token: str


class QuestionRequest(BaseModel):

    question: str
    chat_id: Optional[int] = None


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():

    init_db()


# ============================================================
# LOGIN
# ============================================================

@app.post("/api/login")
async def login(
    data: LoginRequest,
):

    # --------------------------------------------------------
    # CLOUDFLARE TURNSTILE VERIFICATION
    # --------------------------------------------------------

    if not data.turnstile_token.strip():

        raise HTTPException(
            status_code=400,
            detail=(
                "Please complete the security verification."
            ),
        )

    try:

        turnstile_valid = verify_turnstile(
            data.turnstile_token
        )

    except requests.RequestException:

        raise HTTPException(
            status_code=503,
            detail=(
                "Security verification service is "
                "temporarily unavailable. Please try again."
            ),
        )

    except RuntimeError:

        raise HTTPException(
            status_code=500,
            detail=(
                "Security verification is not configured "
                "correctly on the server."
            ),
        )

    if not turnstile_valid:

        raise HTTPException(
            status_code=403,
            detail=(
                "Security verification failed. "
                "Please try again."
            ),
        )

    # --------------------------------------------------------
    # USERNAME / PASSWORD
    # --------------------------------------------------------

    user = get_user(
        data.username.strip()
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid username or password."
            ),
        )

    if not verify_password(
        data.password,
        user["password_hash"],
        user["password_salt"],
    ):

        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid username or password."
            ),
        )

    # --------------------------------------------------------
    # BLOCK CHECK
    # --------------------------------------------------------

    if is_user_blocked(user):

        user = get_user_by_id(
            user["id"]
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message":
                    "Your account is blocked.",
                "blocked_until":
                    user["blocked_until"],
                "remaining_seconds":
                    remaining_block_time(user),
            },
        )

    # --------------------------------------------------------
    # CREATE SESSION
    # --------------------------------------------------------

    token = create_session(
        user["id"]
    )

    return {
        "token": token,
        "username":
            user["username"],
        "off_topic_count":
            user["off_topic_count"],
        "max_off_topic":
            MAX_OFF_TOPIC,
    }


# ============================================================
# LOGOUT
# ============================================================

@app.post("/api/logout")
async def logout(
    authorization: Optional[str] = Header(None),
):

    if (
        authorization
        and authorization.startswith(
            "Bearer "
        )
    ):

        token = authorization[7:]

        sessions.pop(
            token,
            None,
        )

    return {
        "message":
            "Logged out."
    }


# ============================================================
# CURRENT USER
# ============================================================

@app.get("/api/me")
async def me(
    authorization: Optional[str] = Header(None),
):

    user = get_current_user(
        authorization
    )

    if is_user_blocked(user):

        user = get_user_by_id(
            user["id"]
        )

        return {
            "username":
                user["username"],
            "blocked":
                True,
            "blocked_until":
                user["blocked_until"],
            "remaining_seconds":
                remaining_block_time(user),
            "off_topic_count":
                user["off_topic_count"],
            "max_off_topic":
                MAX_OFF_TOPIC,
        }

    return {
        "username":
            user["username"],
        "blocked":
            False,
        "blocked_until":
            None,
        "remaining_seconds":
            0,
        "off_topic_count":
            user["off_topic_count"],
        "max_off_topic":
            MAX_OFF_TOPIC,
    }


# ============================================================
# CHAT HISTORY API
# ============================================================

@app.post("/api/chats")
async def create_chat(
    authorization: Optional[str] = Header(None),
):

    user = get_current_user(authorization)

    chat_id = create_chat_session(
        user["id"]
    )

    return {
        "id": chat_id,
        "title": "New chat",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


@app.get("/api/chats")
async def list_chats(
    authorization: Optional[str] = Header(None),
):

    user = get_current_user(authorization)

    chats = get_chat_sessions(
        user["id"]
    )

    if not chats:
        chat_id = create_chat_session(
            user["id"]
        )
        chats = get_chat_sessions(
            user["id"]
        )
    else:
        chat_id = int(chats[0]["id"])

    return {
        "chats": [dict(chat) for chat in chats],
        "active_chat_id": chat_id,
    }


@app.get("/api/chats/{chat_id}")
async def get_chat(
    chat_id: int,
    authorization: Optional[str] = Header(None),
):

    user = get_current_user(authorization)

    chat = get_chat_session(
        chat_id,
        user["id"],
    )

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    return {
        "chat": dict(chat),
        "messages": [
            dict(message)
            for message in get_chat_messages(chat_id)
        ],
    }


@app.delete("/api/chats/{chat_id}")
async def delete_chat(
    chat_id: int,
    authorization: Optional[str] = Header(None),
):

    user = get_current_user(authorization)

    chat = get_chat_session(
        chat_id,
        user["id"],
    )

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    deleted = delete_chat_session(
        chat_id,
        user["id"],
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    await reset_chat_team(
        user["id"],
        chat_id,
    )

    chats = get_chat_sessions(
        user["id"]
    )

    if not chats:
        new_chat_id = create_chat_session(
            user["id"]
        )
        chats = get_chat_sessions(
            user["id"]
        )
    else:
        new_chat_id = int(chats[0]["id"])

    return {
        "chats": [dict(item) for item in chats],
        "active_chat_id": new_chat_id,
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/api/chat")
async def chat(
    data: QuestionRequest,
    authorization: Optional[str] = Header(None),
):

    question = data.question.strip()

    if not question:

        raise HTTPException(
            status_code=400,
            detail=(
                "Question cannot be empty."
            ),
        )

    user = get_current_user(
        authorization
    )

    user_id = user["id"]

    # --------------------------------------------------------
    # RESOLVE CHAT
    # --------------------------------------------------------

    chat_id = data.chat_id

    if chat_id is None:

        chat_id = create_chat_session(
            user_id
        )

    else:

        chat = get_chat_session(
            chat_id,
            user_id,
        )

        if chat is None:
            raise HTTPException(
                status_code=404,
                detail="Chat not found.",
            )

    # --------------------------------------------------------
    # CHECK BLOCK
    # --------------------------------------------------------

    if is_user_blocked(user):

        user = get_user_by_id(
            user_id
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message":
                    "Your account is blocked "
                    "for 24 hours.",
                "blocked_until":
                    user["blocked_until"],
                "remaining_seconds":
                    remaining_block_time(user),
            },
        )

    # --------------------------------------------------------
    # AFTER 3 OFF-TOPIC QUESTIONS
    # --------------------------------------------------------

    if (
        user["off_topic_count"]
        >= MAX_OFF_TOPIC
        and not looks_relevant(question)
    ):

        blocked_until = (
            datetime.now(timezone.utc)
            + timedelta(
                hours=BLOCK_HOURS
            )
        ).isoformat()

        update_off_topic_count(
            user_id,
            MAX_OFF_TOPIC,
            blocked_until,
        )

        await reset_user_teams(
            user_id
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message":
                    "Your account is blocked "
                    "for 24 hours.",
                "blocked_until":
                    blocked_until,
                "remaining_seconds":
                    BLOCK_HOURS * 3600,
            },
        )

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    add_chat_message(
        chat_id,
        "user",
        question,
    )

    set_chat_title_if_new(
        chat_id,
        question,
    )

    # --------------------------------------------------------
    # RUN AUTOGEN
    # --------------------------------------------------------

    try:

        (
            _result,
            answer,
            off_topic,
            _detected_last_agent,
        ) = await run_chat_turn(
            user_id,
            chat_id,
            question,
        )

    except Exception as exc:

        # Never keep a broken Swarm alive.
        await reset_chat_team(
            user_id,
            chat_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "An error occurred while "
                "processing the question: "
                f"{str(exc)[:500]}"
            ),
        )

    # --------------------------------------------------------
    # OFF-TOPIC
    # --------------------------------------------------------

    if off_topic:

        new_count = (
            user["off_topic_count"]
            + 1
        )

        blocked_until = None

        if new_count >= MAX_OFF_TOPIC:

            blocked_until = (
                datetime.now(
                    timezone.utc
                )
                + timedelta(
                    hours=BLOCK_HOURS
                )
            ).isoformat()

        update_off_topic_count(
            user_id,
            new_count,
            blocked_until,
        )

        await reset_user_teams(
            user_id
        )

        add_chat_message(
            chat_id,
            "assistant",
            OFF_TOPIC_TAG,
        )

        if blocked_until:

            return {
                "chat_id": chat_id,
                "answer":
                    OFF_TOPIC_TAG,
                "off_topic_count":
                    new_count,
                "max_off_topic":
                    MAX_OFF_TOPIC,
                "blocked":
                    True,
                "blocked_until":
                    blocked_until,
                "remaining_seconds":
                    BLOCK_HOURS * 3600,
            }

        return {
            "chat_id": chat_id,
            "answer":
                OFF_TOPIC_TAG,
            "off_topic_count":
                new_count,
            "max_off_topic":
                MAX_OFF_TOPIC,
            "blocked":
                False,
            "blocked_until":
                None,
            "remaining_seconds":
                0,
        }

    # --------------------------------------------------------
    # NORMAL ANSWER
    # --------------------------------------------------------

    add_chat_message(
        chat_id,
        "assistant",
        answer,
    )

    current_user = get_user_by_id(
        user_id
    )

    return {
        "chat_id": chat_id,
        "answer":
            answer,
        "off_topic_count":
            current_user[
                "off_topic_count"
            ],
        "max_off_topic":
            MAX_OFF_TOPIC,
        "blocked":
            False,
        "blocked_until":
            None,
        "remaining_seconds":
            0,
    }


# ============================================================
# FRONTEND
# ============================================================

@app.get("/")
async def root():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


@app.get("/chat")
async def chat_page():

    return FileResponse(
        FRONTEND_DIR / "chat.html"
    )


app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR
    ),
    name="static",
)