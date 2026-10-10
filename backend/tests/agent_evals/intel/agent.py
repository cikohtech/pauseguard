"""The Scam-Intel agent (with its search sub-agent) as the orchestrator builds it, plus an
in-memory watchlist seeded from data/seed for its `watchlist_lookup` tool (ADK eval entry)."""

from __future__ import annotations

from contextlib import ExitStack

from google.adk.agents import BaseAgent

from app.agents.intel_agent import IntelAgent
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.tools.watchlist import use_state


async def get_agent_async() -> tuple[BaseAgent, ExitStack]:
    state = MemoryStateRepo()
    await seed_state(state)
    stack = ExitStack()
    stack.enter_context(use_state(state))  # kept open for the eval run
    return IntelAgent().agent, stack
