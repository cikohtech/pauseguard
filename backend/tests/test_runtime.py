"""The shared agent runtime: one retry, token metering, the shared model instance, prompt
loading, and hedged requests (tail latency) including cancellation by an outer timeout."""

from __future__ import annotations

import asyncio
import time

import pytest
from google.adk.models import Gemini
from google.genai import types

from app.agents import _runtime
from app.agents._runtime import AgentRunner, load_prompt, parse_json_object, resolve_model
from app.agents.explainer_agent import build_agent
from app.config import Settings
from app.models.schemas import CustomerMessageDraft
from tests.fakes import FakeLlm, fake

GOOD = {"headline": "h", "body": "b"}
PARTS = [types.Part.from_text(text="Verdict: AMBER")]


def runner(llm: FakeLlm, hedge_after: float | None = None) -> AgentRunner:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    return AgentRunner(build_agent(llm, s), hedge_after=hedge_after)


def parse(text: str) -> CustomerMessageDraft:
    return CustomerMessageDraft.model_validate(parse_json_object(text))


async def test_fast_answer_needs_no_hedge() -> None:
    llm = fake(GOOD)
    run = await runner(llm, hedge_after=0.5).run(PARTS, parse)
    assert run.output == CustomerMessageDraft(**GOOD) and run.attempts == 1
    assert len(llm.requests) == 1 and run.tokens.in_ == 1000 and run.tokens.out == 250


async def test_a_slow_answer_is_hedged_and_the_first_answer_wins() -> None:
    llm = fake(GOOD, {"headline": "second", "body": "b"}, delays=[2.0, 0.0])
    t = time.perf_counter()
    run = await runner(llm, hedge_after=0.05).run(PARTS, parse)
    assert time.perf_counter() - t < 1.0  # did not wait for the slow first request
    assert run.output and run.output.headline == "second" and len(llm.requests) == 2


async def test_both_copies_failing_counts_as_one_failed_attempt() -> None:
    llm = fake(RuntimeError("stuck"), RuntimeError("also"), GOOD, delays=[0.2, 0.0, 0.0])
    run = await runner(llm, hedge_after=0.05).run(PARTS, parse)
    assert run.output == CustomerMessageDraft(**GOOD) and run.attempts == 2
    assert len(llm.requests) == 3


async def test_a_fast_failure_is_retried_without_a_hedge() -> None:
    llm = fake(RuntimeError("500"), GOOD)
    run = await runner(llm, hedge_after=0.5).run(PARTS, parse)
    assert run.output and run.attempts == 2 and len(llm.requests) == 2


async def test_an_outer_timeout_cancels_both_copies() -> None:
    llm = fake(GOOD, GOOD, delays=[0.5, 0.5])
    r = runner(llm, hedge_after=0.05)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(r.run(PARTS, parse), 0.15)
    await asyncio.sleep(0.6)
    listed = await r.sessions.list_sessions(app_name=_runtime.APP_NAME, user_id=_runtime.USER_ID)
    assert listed.sessions == []  # both calls were cancelled and cleaned up their sessions


async def test_two_bad_answers_give_no_output() -> None:
    run = await runner(fake("nope", {"headline": 1})).run(PARTS, parse)
    assert run.failed and run.attempts == 2 and run.error and "invalid output" in run.error


def test_one_shared_gemini_per_model_name() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    a, b = resolve_model(None, s), resolve_model(s.gemini_model, s)
    assert isinstance(a, Gemini) and a is b
    llm = fake()
    assert resolve_model(llm, s) is llm


def test_prompts_lose_their_changelog_comment() -> None:
    for name in ("evidence", "intel", "search", "explainer", "casefile"):
        text = load_prompt(name)
        assert text and "<!--" not in text and "Changelog" not in text


def test_parse_json_object() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    for bad in ("", "[1]", "nope"):
        with pytest.raises(ValueError):
            parse_json_object(bad)
