"""Interactive console chat with the backend / frontend / manager RAG team.

Run:
    python main.py
Then type questions. Type 'exit' to quit.
"""
import asyncio

from autogen_agentchat.ui import Console

from agents.team import build_team


async def main():
    team = build_team()
    print("Team ready. Ask a backend, frontend, or manager/process question ('exit' to quit).\n")
    while True:
        task = input("You: ").strip()
        if task.lower() in {"exit", "quit"}:
            break
        if not task:
            continue
        await Console(team.run_stream(task=task))
        await team.reset()


if __name__ == "__main__":
    asyncio.run(main())
