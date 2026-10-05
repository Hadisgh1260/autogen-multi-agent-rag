import asyncio
import hashlib
import hmac
import secrets
import sqlite3

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

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
# SETTINGS
# ============================================================

MAX_OFF_TOPIC = 3
BLOCK_HOURS = 24
OFF_TOPIC_TAG = "[OFF-TOPIC]"


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

# One Swarm per logged-in user.
# This keeps the AutoGen conversation context between requests.

user_teams = {}
team_locks = {}

# The specialist that produced the previous completed answer.
last_agents = {}

# Last answer is stored separately so that if the AutoGen context
# becomes invalid/too large, we can rebuild the immediate context.
last_answers = {}


def get_team(user_id: int):

    if user_id not in user_teams:
        user_teams[user_id] = build_team()

    if user_id not in team_locks:
        team_locks[user_id] = asyncio.Lock()

    return user_teams[user_id]


async def reset_user_team(user_id: int):

    team = user_teams.get(user_id)

    if team is not None:

        try:
            await team.reset()

        except Exception:
            # If the existing team is already broken,
            # discard it and create a fresh one next time.
            pass

    user_teams.pop(
        user_id,
        None,
    )

    last_agents.pop(
        user_id,
        None,
    )

    last_answers.pop(
        user_id,
        None,
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
    user_id: int,
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

        last_agents[user_id] = (
            detected_last_agent
        )

    # --------------------------------------------------------
    # SAVE LAST ANSWER
    # --------------------------------------------------------

    if answer:

        last_answers[user_id] = answer

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
    question: str,
):

    team = get_team(user_id)

    lock = team_locks[user_id]

    async with lock:

        previous_agent = last_agents.get(
            user_id
        )

        previous_answer = last_answers.get(
            user_id
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
                user_id,
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

            await reset_user_team(
                user_id
            )

            retry_team = get_team(
                user_id
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
                    user_id,
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


class QuestionRequest(BaseModel):

    question: str


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

        await reset_user_team(
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
            question,
        )

    except Exception as exc:

        # Never keep a broken Swarm alive.
        await reset_user_team(
            user_id
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

        await reset_user_team(
            user_id
        )

        if blocked_until:

            return {
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

    current_user = get_user_by_id(
        user_id
    )

    return {
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