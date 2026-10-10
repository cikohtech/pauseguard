"""Search agent (AGENTS_SPEC §3, ARCHITECTURE D4): an LlmAgent whose only tool is Google Search
grounding. `google_search` is a model built-in that cannot sit next to function tools, so the
Scam-Intel agent calls this agent through `AgentTool`.

AgentTool does not forward the nested run's events, so `record_grounding` (an
after_model_callback) captures what each search really returned: the request, the grounding
URLs and the Search suggestions chip. The Scam-Intel agent uses these records as the sources of
its findings, never URLs the model typed itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import BaseLlm, LlmResponse
from google.adk.tools import google_search

from app.agents._runtime import count_tokens, generate_config, load_prompt, resolve_model
from app.config import Settings, get_settings

AGENT_NAME = "search_agent"
DESCRIPTION = (
    "Searches the web with Google Search to find out whether one organisation, website or "
    "investment platform is legitimate or reported as a scam in Singapore/Asia. "
    "Send one entity per request."
)


@dataclass
class SearchRecord:
    request: str
    text: str = ""
    queries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    entry_point_html: str | None = None


_RECORDS: ContextVar[list[SearchRecord] | None] = ContextVar("search_records", default=None)


@contextmanager
def recording() -> Iterator[list[SearchRecord]]:
    """Collect a SearchRecord for every search made inside the block (and its child tasks)."""
    records: list[SearchRecord] = []
    token = _RECORDS.set(records)
    try:
        yield records
    finally:
        _RECORDS.reset(token)


def record_grounding(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    """after_model_callback: keep the final answer of each search with its grounding."""
    records = _RECORDS.get()
    content = llm_response.content
    if records is None or content is None or not content.parts:
        return None
    text = "".join(p.text for p in content.parts if p.text and not p.thought).strip()
    if not text:  # a function-call turn, not the answer
        return None
    user = callback_context.user_content
    request = "".join(p.text or "" for p in (user.parts or [])).strip() if user else ""
    gm = llm_response.grounding_metadata
    sources: list[str] = []
    for chunk in (gm.grounding_chunks or []) if gm else []:
        if chunk.web and chunk.web.uri and chunk.web.uri not in sources:
            sources.append(chunk.web.uri)
    records.append(
        SearchRecord(
            request=request,
            text=text,
            queries=list(gm.web_search_queries or []) if gm else [],
            sources=sources,
            entry_point_html=(
                gm.search_entry_point.rendered_content if gm and gm.search_entry_point else None
            ),
        )
    )
    return None


def build_search_agent(
    model: str | BaseLlm | None = None, settings: Settings | None = None
) -> LlmAgent:
    settings = settings or get_settings()
    return LlmAgent(
        name=AGENT_NAME,
        description=DESCRIPTION,
        model=resolve_model(model, settings),
        static_instruction=load_prompt("search"),
        tools=[google_search],
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=generate_config(settings),
        after_model_callback=[count_tokens, record_grounding],
    )
