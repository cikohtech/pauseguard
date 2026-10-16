"""Shared plumbing for the LLM agents (CLAUDE.md rule 4).

    runner = AgentRunner(llm_agent)
    run = await runner.run(parts, parse=MyModel.model_validate_json-ish, check_id=...)
    run.output     the parsed model, or None after one retry (the caller falls back)
    run.tokens     every model call in the run, including nested AgentTool runs

Each agent gets one ADK Runner and a fresh in-memory session per call (deleted afterwards).
ADK's own output validation is not used: we parse and validate the final text ourselves, retry
once, and leave the safe fallback to the caller. Tokens are counted by `count_tokens`, an
`after_model_callback` that every agent registers, into a per-run meter held in a context
variable, so a search agent running inside the Scam-Intel agent's AgentTool is counted too.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import aclosing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm, Gemini, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from app.config import Settings
from app.log import get_logger
from app.models.schemas import TokenUsage

log = get_logger(__name__)

APP_NAME = "pauseguard"
USER_ID = "pauseguard"
MAX_ATTEMPTS = 2  # the first call plus one retry
PROMPTS_DIR = Path(__file__).with_name("prompts")

_METER: ContextVar[TokenUsage | None] = ContextVar("token_meter", default=None)


def count_tokens(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    """after_model_callback: add this model call's usage to the current run's meter."""
    meter = _METER.get()
    if meter is not None and (u := llm_response.usage_metadata):
        meter.in_ += u.prompt_token_count or 0
        meter.out += (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
    return None


@contextmanager
def metering() -> Iterator[TokenUsage]:
    """A fresh token meter for everything awaited inside the block (and its child tasks)."""
    meter = TokenUsage()
    token = _METER.set(meter)
    try:
        yield meter
    finally:
        _METER.reset(token)


# Quota (429) or an overloaded model (503): the genai client retries with exponential backoff
# (0.5 s, then 1 s, with jitter) before the error reaches the AgentRunner's own retry and the
# safe fallback. Short on purpose: the customer-facing budget is AGENT_TIMEOUT_SECONDS.
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=3, initial_delay=0.5, max_delay=2.0, exp_base=2.0, http_status_codes=[429, 503]
)


@lru_cache
def shared_model(model_id: str) -> Gemini:
    """One Gemini instance for every agent in the process. Given a model *name*, ADK builds a
    new Gemini (and genai Client) on every call, which reloads credentials (locally a `gcloud`
    subprocess), fetches a new token and opens a new TLS connection each time. One shared
    instance keeps one client per event loop: credentials once, connections kept alive."""
    return Gemini(model=model_id, retry_options=RETRY_OPTIONS)


async def ping_model(model_id: str) -> None:
    """GET /health's model check: count_tokens is free and generates nothing, but it goes through
    the same client, credentials and Vertex AI endpoint as the agents. Raises when unreachable."""
    client = shared_model(model_id).api_client
    await client.aio.models.count_tokens(model=model_id, contents="ping")


def resolve_model(model: str | BaseLlm | None, settings: Settings) -> BaseLlm:
    """An explicit BaseLlm (tests) is used as is; a name or None gets the shared instance."""
    if isinstance(model, BaseLlm):
        return model
    return shared_model(model or settings.gemini_model)


def generate_config(settings: Settings, *, media: bool = False) -> types.GenerateContentConfig:
    """3.8 Flash ignores temperature/top_p and rejects penalties: only the thinking level (and,
    for agents that read images or PDFs, the media resolution) is set."""
    resolution = None
    if media and settings.gemini_media_resolution != "DEFAULT":
        resolution = types.MediaResolution(f"MEDIA_RESOLUTION_{settings.gemini_media_resolution}")
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel(settings.gemini_thinking_level)
        ),
        media_resolution=resolution,
    )


def load_prompt(name: str) -> str:
    """prompts/<name>.md without its leading HTML comment (the changelog)."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """Model text -> dict. Code fences are tolerated; anything else that isn't an object raises."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    if not raw:
        raise ValueError("empty model output")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


def short_error(e: BaseException, limit: int = 300) -> str:
    return str(e).replace("\n", " ")[:limit]


def neutralise(text: str) -> str:
    """Untrusted text cannot open or close our delimiters: '</evidence>' becomes '‹/evidence>'."""
    return _TAG_BREAKOUT.sub(r"‹\1", text)


_TAG_BREAKOUT = re.compile(
    r"<(/?\s*(?:evidence|transfer|customer_answer|system|verdict|flags|case|intel)\b)", re.I
)


@dataclass
class AgentRun[T]:
    output: T | None
    attempts: int
    latency_ms: int
    tokens: TokenUsage
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.output is None


class AgentRunner:
    """One ADK Runner around one LlmAgent; every call gets a fresh session."""

    def __init__(
        self,
        agent: LlmAgent,
        *,
        max_llm_calls: int | None = None,
        hedge_after: float | None = None,
    ):
        self.agent = agent
        # Tail latency: with no answer after `hedge_after` seconds, send the same request again
        # and take whichever answers first (the slower one is cancelled).
        self.hedge_after = hedge_after or None
        self.sessions = InMemorySessionService()
        self.runner = Runner(app_name=APP_NAME, agent=agent, session_service=self.sessions)
        # A ceiling on model calls per invocation (ADK's default is 500); bounds tool loops.
        self.run_config = RunConfig(max_llm_calls=max_llm_calls) if max_llm_calls else None

    async def call(self, parts: list[types.Part]) -> str:
        """One invocation; returns the agent's final text (thoughts excluded)."""
        session = await self.sessions.create_session(app_name=APP_NAME, user_id=USER_ID)
        text = ""
        events = self.runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=types.Content(role="user", parts=parts),
            run_config=self.run_config,
        )
        try:
            # aclosing: a cancelled call (timeout, losing hedge) closes ADK's generator in this
            # task, not later from the garbage collector in another context.
            async with aclosing(events):
                async for event in events:
                    if event.error_code:
                        raise RuntimeError(f"model error {event.error_code}: {event.error_message}")
                    if (
                        event.author == self.agent.name
                        and event.is_final_response()
                        and event.content
                    ):
                        text = "".join(
                            p.text for p in event.content.parts or [] if p.text and not p.thought
                        )
        finally:
            await self.sessions.delete_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=session.id
            )
        return text

    async def call_hedged(self, parts: list[types.Part]) -> str:
        """`call`, plus a second identical request if the first is slow. First success wins; if
        both fail, the first error is raised. Tokens of both calls are metered."""
        if not self.hedge_after:
            return await self.call(parts)
        tasks = [asyncio.create_task(self.call(parts))]
        try:
            done, _ = await asyncio.wait(tasks, timeout=self.hedge_after)
            if not done:
                log.info("agent_hedged", agent=self.agent.name, after_s=self.hedge_after)
                tasks.append(asyncio.create_task(self.call(parts)))
            pending: set[asyncio.Task[str]] = set(tasks)
            errors: list[BaseException] = []
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if (e := task.exception()) is None:
                        return task.result()
                    errors.append(e)
            raise errors[0]
        finally:
            for task in tasks:
                task.cancel()  # a no-op for finished tasks

    async def run[T](
        self,
        parts: list[types.Part],
        parse: Callable[[str], T],
        *,
        check_id: str | None = None,
        attempts: int = MAX_ATTEMPTS,
    ) -> AgentRun[T]:
        """Call, parse, retry once on a bad answer or a model error. Never raises for those."""
        start = time.perf_counter()
        output: T | None = None
        error: str | None = None
        attempt = 0
        with metering() as tokens:
            for attempt in range(1, attempts + 1):
                try:
                    output = parse(await self.call_hedged(parts))
                    error = None
                    break
                except (ValueError, ValidationError) as e:  # bad JSON or schema
                    error = f"invalid output: {short_error(e)}"
                except Exception as e:  # model or network error: retried, then the fallback
                    error = f"{type(e).__name__}: {short_error(e)}"
                log.warning(
                    "agent_attempt_failed",
                    agent=self.agent.name,
                    check_id=check_id,
                    attempt=attempt,
                    error=error,
                )
        return AgentRun(
            output=output,
            attempts=attempt,
            latency_ms=round((time.perf_counter() - start) * 1000),
            tokens=tokens,
            error=error,
        )
