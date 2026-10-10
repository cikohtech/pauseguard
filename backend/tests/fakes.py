"""A fake Gemini for unit tests: the real ADK Runner and agents, canned model answers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.models._capabilities import LlmCapabilities
from google.genai import types


def usage(prompt: int = 1000, out: int = 200, thoughts: int = 50) -> Any:
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thoughts
    )


def call(name: str, **args: Any) -> LlmResponse:
    """A model turn that calls a tool."""
    return LlmResponse(
        content=types.Content(
            role="model", parts=[types.Part.from_function_call(name=name, args=args)]
        ),
        usage_metadata=usage(500, 20, 0),
    )


def grounded(text: str, uris: list[str], html: str | None = "<div>chip</div>") -> LlmResponse:
    """A search answer with Google Search grounding metadata."""
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part.from_text(text=text)]),
        grounding_metadata=types.GroundingMetadata(
            grounding_chunks=[
                types.GroundingChunk(web=types.GroundingChunkWeb(uri=u, title=f"t{i}"))
                for i, u in enumerate(uris)
            ],
            web_search_queries=["q"],
            search_entry_point=types.SearchEntryPoint(rendered_content=html) if html else None,
        ),
        usage_metadata=usage(300, 80, 0),
    )


class FakeLlm(BaseLlm):
    """Replays canned responses in order: a dict (sent as JSON), a str, an LlmResponse, or an
    Exception (raised). Each answer waits `delays[i]` seconds if given, else `delay`."""

    model: str = "gemini-fake"
    responses: list[Any] = []
    requests: list[LlmRequest] = []
    delay: float = 0.0
    delays: list[float] = []
    schema_with_tools: bool = False

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.schema_with_tools)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        r = self.responses.pop(0)  # taken before waiting, so concurrent calls get their own
        delay = self.delays.pop(0) if self.delays else self.delay
        if delay:
            await asyncio.sleep(delay)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, LlmResponse):
            yield r
            return
        text = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text=text)]),
            usage_metadata=usage(),
        )


def fake(*responses: Any, **kw: Any) -> FakeLlm:
    return FakeLlm(responses=list(responses), requests=[], **kw)


def request_text(req: LlmRequest) -> str:
    """Every text part the model was sent (to assert on what an agent's input contains)."""
    return "\n".join(p.text for c in req.contents for p in c.parts or [] if p.text)
