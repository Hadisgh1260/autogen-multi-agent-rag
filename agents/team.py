"""Builds the backend / frontend / manager agents and wires them into a Swarm team.

Pattern: the manager always speaks first. It either answers directly (using its own
reference book, for process/coordination questions) or explicitly hands off to the
backend or frontend specialist. Whichever agent answers last hands off to "user" to
signal it is done, which ends that turn.
"""
import sys
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import Handoff
from autogen_agentchat.conditions import HandoffTermination, MaxMessageTermination
from autogen_agentchat.teams import Swarm
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient

sys.path.append(str(Path(__file__).parent.parent))
from config import (
    AGENTS,
    AGENT_MODEL,
    OPENAI_API_KEY,
    LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_BASE_URL,
)
from rag.retriever import make_search_tool


# --- Groq compatibility workaround -----------------------------------------
# AutoGen's built-in handoff tools take zero arguments, which produces a JSON
# schema with an empty "properties": {}. Groq's tool-schema validator has a bug
# where it misreads that empty object as "properties missing" and rejects the
# request ("'required' present but 'properties' is missing"), even though the
# schema autogen sends is valid. OpenAI's real API doesn't have this bug.
# Fix: give every handoff tool one harmless optional argument so "properties"
# is never empty. Harmless for OpenAI too, so we apply it unconditionally.
def _handoff_tool_with_dummy_arg(self: Handoff) -> FunctionTool:
    def _handoff_tool(reason: str = "") -> str:
        """reason: brief note on why this handoff is happening (optional)."""
        return self.message

    return FunctionTool(_handoff_tool, name=self.name, description=self.description, strict=False)


Handoff.handoff_tool = property(_handoff_tool_with_dummy_arg)  # type: ignore[assignment]
# -----------------------------------------------------------------------------


def build_model_client() -> OpenAIChatCompletionClient:
    # A handoff is a tool call; if the model fires more than one tool call at once
    # (a handoff plus something else) the Swarm can get confused about who's next.
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
                "(get one at https://console.groq.com/keys)."
            )
        return OpenAIChatCompletionClient(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL,
            # Required whenever base_url is customized: tells AutoGen this model's
            # capabilities since it isn't in its built-in OpenAI model registry.
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "unknown",
                "structured_output": False,
            },
            parallel_tool_calls=False,
        )

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return OpenAIChatCompletionClient(
        model=AGENT_MODEL,
        api_key=OPENAI_API_KEY,
        parallel_tool_calls=False,
    )


def build_specialist(agent_key: str, model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """Backend or frontend agent: answers from its own reference book, then hands off to the user."""
    cfg = AGENTS[agent_key]
    search_tool = make_search_tool(agent_key)
    return AssistantAgent(
        name=agent_key,
        model_client=model_client,
        tools=[search_tool],
        handoffs=["user"],
        # Without this, a tool call's raw output (the retrieved passages) is
        # returned as-is instead of being turned into a written answer.
        reflect_on_tool_use=True,
        description=cfg["description"],
        system_message=(
            f"You are the {agent_key} specialist. {cfg['description']} "
            f"You are only ever engaged by the manager for questions in your domain. "
            f"ALWAYS call your search_{agent_key}_reference_book tool first to check the "
            f"reference material, then answer based on what it returns, citing the source "
            f"names it gives you. Once you have fully answered, hand off to 'user' to finish "
            f"— do not wait for further instructions and do not hand off to anyone else."
        ),
    )


def build_manager(agent_key: str, model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """Manager agent: always sees the question first, routes it, or answers it directly."""
    cfg = AGENTS[agent_key]
    search_tool = make_search_tool(agent_key)
    return AssistantAgent(
        name=agent_key,
        model_client=model_client,
        tools=[search_tool],
        handoffs=["backend", "frontend", "user"],
        # Same fix as the specialists: force a written answer when the manager
        # answers a process question itself, instead of dumping raw passages.
        reflect_on_tool_use=True,
        description=cfg["description"],
        system_message=(
            f"You are the engineering manager. {cfg['description']} "
            f"You always see every incoming question first. For each question, decide:\n"
            f"1. If it is about backend/API/database/server topics, hand off to 'backend' "
            f"immediately — do not answer it yourself.\n"
            f"2. If it is about frontend/UI/framework/browser topics, hand off to 'frontend' "
            f"immediately — do not answer it yourself.\n"
            f"3. If it is about process, planning, prioritization, coordination, or spans both "
            f"domains, call your search_{agent_key}_reference_book tool, answer it yourself "
            f"citing sources, then hand off to 'user' to finish.\n"
            f"When handing off to backend or frontend, do so with no extra commentary — just "
            f"the handoff, so the specialist can take over."
        ),
    )


def build_team():
    """Returns a ready-to-run Swarm of manager, backend, and frontend agents.

    manager MUST be first in the participants list: Swarm starts (and restarts, on
    reset()) with participants[0] as the current speaker.
    """
    model_client = build_model_client()
    manager_agent = build_manager("manager", model_client)
    backend_agent = build_specialist("backend", model_client)
    frontend_agent = build_specialist("frontend", model_client)

    termination = HandoffTermination(target="user") | MaxMessageTermination(10)

    team = Swarm(
        participants=[manager_agent, backend_agent, frontend_agent],
        termination_condition=termination,
    )
    return team
