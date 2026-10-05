"""AutoGen RAG team: manager + backend + frontend."""

import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import Handoff
from autogen_agentchat.conditions import (
    HandoffTermination,
    MaxMessageTermination,
    TextMentionTermination,
)
from autogen_core.tools import FunctionTool
from autogen_agentchat.teams import Swarm
from autogen_ext.models.openai import OpenAIChatCompletionClient
from openai import BadRequestError

from config import (
    AGENTS,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
)
from rag.retriever import make_search_tool


# ---------------------------------------------------------------------------
# Groq / AutoGen compatibility
# ---------------------------------------------------------------------------

def _handoff_tool_with_dummy_arg(self: Handoff) -> FunctionTool:

    def _handoff_tool(reason: str = "") -> str:
        """Internal handoff helper."""
        return self.message

    return FunctionTool(
        _handoff_tool,
        name=self.name,
        description=self.description,
        strict=False,
    )


Handoff.handoff_tool = property(
    _handoff_tool_with_dummy_arg
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OFF_TOPIC_TAG = "[OFF-TOPIC]"


# ---------------------------------------------------------------------------
# Retry client
# ---------------------------------------------------------------------------

class RetryingClient(OpenAIChatCompletionClient):
    """Retry Groq tool-call validation errors."""

    async def create(self, *args, **kwargs):

        last_err = None

        for _ in range(3):

            try:

                return await super().create(
                    *args,
                    **kwargs
                )

            except BadRequestError as e:

                text = str(e)

                if (
                    "tool_use_failed" in text
                    or "Tool call validation failed" in text
                ):

                    last_err = e

                    await asyncio.sleep(0.5)

                    continue

                raise

        raise last_err


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_model_client():

    return RetryingClient(
        model=GROQ_MODEL,
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,

        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": False,
        },

        parallel_tool_calls=False,
    )


# ---------------------------------------------------------------------------
# Specialist agents
# ---------------------------------------------------------------------------

def build_specialist(
    agent_key: str,
    model_client
):

    cfg = AGENTS[agent_key]

    search_tool = make_search_tool(
        agent_key
    )

    return AssistantAgent(

        name=agent_key,

        model_client=model_client,

        tools=[
            search_tool
        ],

        handoffs=[
            "user"
        ],

        reflect_on_tool_use=False,

        description=cfg["description"],

        system_message=(

            f"You are the {agent_key} specialist. "
            f"{cfg['description']}\n\n"

            "SCOPE:\n"

            f"Only answer questions related to "
            f"{agent_key}, software engineering, "
            "or the user's current technical context.\n"

            "A person's name does NOT make a question "
            "off-topic when the question is about that "
            "person's technical responsibilities, "
            "implementation work, software role, or "
            "engineering tasks.\n"

            "For clearly unrelated questions, reply "
            f"with {OFF_TOPIC_TAG} only. "
            "Do not search.\n\n"

            "REFERENCE:\n"

            f"For on-topic questions, search the "
            f"{agent_key} reference first. "

            "Use the retrieved information when relevant "
            "and mention the source name.\n\n"

            "ANSWER:\n"

            "Keep normal answers very short: "
            "2-4 sentences or a small code snippet.\n"

            "Do not add unnecessary theory, background, "
            "alternatives, or edge cases.\n"

            "End with a short question asking whether "
            "the user wants more detail or an example.\n\n"

            "CONVERSATIONAL CONTEXT:\n"

            "Use the previous conversation context naturally.\n"

            "Do not treat a person's name as an unrelated "
            "personal-information question when the person "
            "is being discussed in a technical or engineering "
            "context.\n"

            "For example:\n"

            "User: 'Amirhossein is my backend developer.'\n"

            "User: 'What should he do now?'\n"

            "Understand that 'he' refers to Amirhossein "
            "and that the topic remains backend/software "
            "engineering.\n\n"

            "FOLLOW-UP:\n"

            "Short follow-ups such as 'yes', 'sure', "
            "'why?', 'how?', 'what next?', "
            "'what should he do?', 'what should I do?', "
            "'and then?', or 'how can I handle it?' "
            "refer to the previous technical topic when "
            "the previous conversation provides that context.\n"

            "Answer the follow-up directly and do not "
            "repeat the previous explanation.\n"

            "If the user asks for more detail or an example, "
            "expand the previous answer.\n\n"

            "REFERENCE GAP:\n"

            "If the question is on-topic but the reference "
            "does not cover it, answer briefly from general "
            "knowledge and say that the reference does not "
            "cover it.\n\n"

            "HANDOFF:\n"

            "After answering an on-topic question, "
            "hand off to user.\n"

            "Never hand off to another agent."
        ),
    )


# ---------------------------------------------------------------------------
# Manager agent
# ---------------------------------------------------------------------------

def build_manager(
    agent_key: str,
    model_client
):

    cfg = AGENTS[agent_key]

    search_tool = make_search_tool(
        agent_key
    )

    return AssistantAgent(

        name=agent_key,

        model_client=model_client,

        tools=[
            search_tool
        ],

        handoffs=[
            "backend",
            "frontend",
            "user"
        ],

        reflect_on_tool_use=False,

        description=cfg["description"],

        system_message=(

            "You are the engineering manager and router "
            "for a software engineering team.\n\n"

            "FIRST STEP — UNDERSTAND THE USER:\n"

            "Read the user's message together with the "
            "previous conversation context.\n"

            "Do not classify a message only by isolated "
            "keywords.\n"

            "Understand pronouns, names, implied subjects, "
            "and short follow-up questions from context.\n\n"

            "IMPORTANT CONTEXT RULE:\n"

            "A person's name does not automatically make a "
            "question personal or off-topic.\n"

            "If the person is being discussed as a backend "
            "developer, frontend developer, engineer, "
            "programmer, technical lead, or other technical "
            "role, the conversation remains on-topic.\n\n"

            "Example:\n"

            "User: 'Amirhossein is my backend developer.'\n"

            "User: 'What should he do now?'\n"

            "Interpret 'he' as Amirhossein and understand "
            "that the question is about his backend/software "
            "engineering work.\n\n"

            "Another example:\n"

            "User: 'Sara handles the frontend.'\n"

            "User: 'What should she work on next?'\n"

            "This is a frontend/software-engineering question, "
            "not a personal-information question.\n\n"

            "ON-TOPIC INCLUDES:\n"

            "- Backend development\n"
            "- Frontend development\n"
            "- APIs and web services\n"
            "- Databases\n"
            "- Servers and infrastructure\n"
            "- HTTP and networking concepts related to software\n"
            "- Software architecture\n"
            "- Programming and programming languages\n"
            "- JavaScript, CSS, HTML, browser behavior\n"
            "- Engineering implementation\n"
            "- Debugging\n"
            "- Technical planning\n"
            "- Project implementation\n"
            "- Software development tasks\n"
            "- Questions about what a technical team member "
            "should implement or work on\n\n"

            "OFF-TOPIC INCLUDES:\n"

            "- Personal information unrelated to technical work\n"
            "- Salary\n"
            "- Age\n"
            "- Personal relationships\n"
            "- Personal life\n"
            "- Vacation\n"
            "- Attendance\n"
            "- Private employee information\n"
            "- HR or administrative matters\n"
            "- Company gossip\n"
            "- General knowledge unrelated to software engineering\n"
            "- Topics that cannot reasonably be answered by "
            "a backend, frontend, or software engineering specialist\n\n"

            "CRITICAL OFF-TOPIC RULE:\n"

            "If the question is clearly unrelated to software "
            "engineering, output exactly "
            f"{OFF_TOPIC_TAG}.\n"

            "Do not ask a clarification question.\n"

            "Do not answer the question.\n"

            "Do not search the reference.\n"

            "Do not hand off to another agent.\n"

            "Do not explain why it is off-topic.\n"

            "The entire response must contain only "
            "the off-topic tag.\n\n"

            "ROUTING:\n"

            "- Backend, API, database, server, HTTP, backend "
            "architecture, backend implementation, or backend "
            "development -> backend.\n"

            "- Frontend, UI, CSS, JavaScript, HTML, browser, "
            "or frontend framework -> frontend.\n"

            "- General software engineering, engineering "
            "process, planning, architecture, or technical "
            "coordination -> answer yourself.\n\n"

            "IMPORTANT:\n"

            "For backend/frontend questions, hand off immediately.\n"

            "Do not answer the question yourself first.\n\n"

            "MANAGER ANSWERS:\n"

            "When answering an on-topic question yourself, "
            "keep it to 2-4 sentences.\n"

            "Avoid unnecessary background and theory.\n"

            "End by asking whether the user wants more detail "
            "or an example.\n\n"

            "FOLLOW-UP:\n"

            "Use previous conversation context.\n"

            "Short replies such as 'yes', 'sure', "
            "'what next?', 'what should he do?', "
            "'what should I do?', 'and then?', "
            "'how?', or 'why?' should be interpreted using "
            "the previous technical context.\n"

            "Do not reset the topic simply because the new "
            "message contains no technical keyword.\n"

            "If the previous topic was backend, keep it "
            "backend unless the user clearly changes topic.\n"

            "If the previous topic was frontend, keep it "
            "frontend unless the user clearly changes topic.\n\n"

            "OFF-TOPIC OUTPUT:\n"

            f"For clearly unrelated questions, output only "
            f"{OFF_TOPIC_TAG}."
        ),
    )


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

def build_team():

    model_client = build_model_client()


    manager_agent = build_manager(
        "manager",
        model_client
    )


    backend_agent = build_specialist(
        "backend",
        model_client
    )


    frontend_agent = build_specialist(
        "frontend",
        model_client
    )


    termination = (
        HandoffTermination(
            target="user"
        )

        |

        TextMentionTermination(
            OFF_TOPIC_TAG
        )

        |

        MaxMessageTermination(
            8
        )
    )


    return Swarm(

        participants=[
            manager_agent,
            backend_agent,
            frontend_agent,
        ],

        termination_condition=
            termination,
    )