"""Scam-Intel agent (AGENTS_SPEC §3): checks the entities nobody knows yet.

    run = await intel.investigate(IntelRequest(...), state=state)
    run.result     IntelResult: the watchlist matches the code found, plus grounded web findings

Tools: `watchlist_lookup` (FunctionTool) and `AgentTool(search_agent)` (Google Search). The code
does the watchlist lookups the verdict depends on before this agent runs (they are in the input),
so the LLM's job is to choose which unknown websites, domains and platforms to search, and to
summarise what it found. Guard rails in code, not just in the prompt:
- at most `INTEL_MAX_SEARCHES` searches per check, and never a phone or account number
  (`before_tool_callback`);
- a finding must belong to a search that was really made; its `sources` are that search's
  grounding URLs (search_agent.record_grounding), never URLs the model wrote;
- watchlist matches come from the code and the tool, never from the model's answer.
If there is nothing worth searching the LLM is not called at all. A failed run keeps the
watchlist matches and has no web findings; the verdict never depends on this agent.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools import AgentTool, BaseTool, FunctionTool, ToolContext
from google.genai import types

from app.agents import search_agent as search
from app.agents._runtime import (
    AgentRunner,
    count_tokens,
    generate_config,
    load_prompt,
    neutralise,
    parse_json_object,
    resolve_model,
)
from app.config import Settings, get_settings
from app.data.base import StateRepo
from app.data.normalise import normalise_domain, normalise_watchlist_value
from app.log import get_logger
from app.models.schemas import (
    ClaimedSender,
    Entities,
    IntelFindings,
    IntelResult,
    TokenUsage,
    Typology,
    WatchlistMatch,
    WebFinding,
)
from app.tools.watchlist import collecting, entities_from_text, use_state, watchlist_lookup

log = get_logger(__name__)

AGENT_NAME = "intel_agent"
MAX_LLM_CALLS = 6  # decide + searches + answer, with room for one watchlist call and a retry

_SEARCHES: ContextVar[list[str] | None] = ContextVar("intel_searches", default=None)


@dataclass
class IntelRequest:
    entities: Entities
    watchlist_matches: list[WatchlistMatch] = field(default_factory=list)
    typology: Typology = "UNKNOWN"
    confidence: float = 0.0
    claimed_sender: ClaimedSender | None = None
    summary: str | None = None
    check_id: str | None = None


@dataclass
class IntelRun:
    result: IntelResult
    called_model: bool
    failed: bool
    latency_ms: int
    tokens: TokenUsage
    searches: int = 0
    error: str | None = None


def _listed(matches: list[WatchlistMatch]) -> set[tuple[str, str]]:
    return {(m.type, m.value) for m in matches}


def _status(type_: str, value: str, listed: set[tuple[str, str]]) -> str:
    keys = [(type_, normalise_watchlist_value(type_, value))]  # type: ignore[arg-type]
    if type_ == "URL":
        keys.append(("DOMAIN", normalise_domain(value)))
    return "ON WATCHLIST" if any(k in listed for k in keys) else "not listed"


def unknown_web_entities(req: IntelRequest) -> list[str]:
    """URLs not on the watchlist (by URL or domain) and organisations: what search could add."""
    listed = _listed(req.watchlist_matches)
    urls = [u for u in req.entities.urls if _status("URL", u, listed) == "not listed"]
    return urls + req.entities.orgs


def build_input(req: IntelRequest) -> str:
    listed = _listed(req.watchlist_matches)
    e = req.entities
    case = [f"Typology guess: {req.typology} (confidence {req.confidence:.2f})"]
    if s := req.claimed_sender:
        who = ", ".join(x for x in (s.name, s.claimed_org, s.channel) if x)
        if who:
            case.append(f"Claimed sender: {neutralise(who)}")
    if req.summary:
        case.append(f"Summary: {neutralise(req.summary)}")
    lines = ["Already checked against the watchlist (do not look these up again):"]
    lines += [f"- PHONE {neutralise(p)}: {_status('PHONE', p, listed)}" for p in e.phones]
    lines += [f"- URL {neutralise(u)}: {_status('URL', u, listed)}" for u in e.urls]
    lines += [f"- ACCOUNT {neutralise(a)}: {_status('ACCOUNT', a, listed)}" for a in e.accounts]
    if len(lines) == 1:
        lines.append("- (none)")
    lines.append("Organisations named: " + (neutralise(", ".join(e.orgs)) or "(none)"))
    lines.append("Apps named: " + (neutralise(", ".join(e.apps)) or "(none)"))
    case_block = "<case>\n" + "\n".join(case) + "\n</case>"
    return case_block + "\n<entities>\n" + "\n".join(lines) + "\n</entities>"


@contextmanager
def _search_budget() -> Iterator[list[str]]:
    used: list[str] = []
    token = _SEARCHES.set(used)
    try:
        yield used
    finally:
        _SEARCHES.reset(token)


def _same_request(a: str, b: str) -> bool:
    a, b = " ".join(a.casefold().split()), " ".join(b.casefold().split())
    return bool(a and b) and (a == b or a in b or b in a)


def ground_findings(
    findings: IntelFindings, records: list[search.SearchRecord]
) -> list[WebFinding]:
    """Keep only findings that belong to a real search; their sources are its grounding URLs."""
    out: list[WebFinding] = []
    for f in findings.web_findings:
        record = next((r for r in records if _same_request(f.query, r.request)), None)
        if record is None:
            log.warning("intel_ungrounded_finding_dropped", query=f.query[:120])
            continue
        out.append(
            WebFinding(
                query=record.request,
                finding=f.finding,
                sources=record.sources,
                risk=f.risk,
                search_entry_point_html=record.entry_point_html,
            )
        )
    return out


class IntelAgent:
    def __init__(
        self,
        model: str | BaseLlm | None = None,
        settings: Settings | None = None,
        *,
        search_model: str | BaseLlm | None = None,
    ):
        self.settings = settings or get_settings()
        self.settings.export_sdk_env()
        self.max_searches = self.settings.intel_max_searches
        self.search_agent = search.build_search_agent(search_model or model, self.settings)
        self.agent = LlmAgent(
            name=AGENT_NAME,
            description="Checks unknown websites, domains and platforms from a scam conversation.",
            model=resolve_model(model, self.settings),
            static_instruction=load_prompt("intel"),
            tools=[
                FunctionTool(watchlist_lookup),
                AgentTool(self.search_agent, propagate_grounding_metadata=True),
            ],
            output_schema=IntelFindings,
            include_contents="none",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=generate_config(self.settings),
            before_tool_callback=self._guard_tools,
            after_model_callback=count_tokens,
        )
        self._runner = AgentRunner(self.agent, max_llm_calls=MAX_LLM_CALLS)

    def _guard_tools(
        self, tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, Any] | None:
        """Budget and scope for search, enforced in code. Returning a dict skips the tool."""
        if tool.name != search.AGENT_NAME:
            return None
        used = _SEARCHES.get()
        request = str(args.get("request", ""))
        if used is None:
            return None
        if len(used) >= self.max_searches:
            return {"error": f"Search budget used up ({self.max_searches} per check)."}
        found = entities_from_text(request)
        if found.phones or found.accounts:
            return {"error": "Phone numbers and bank accounts are never searched."}
        used.append(request)
        return None

    async def investigate(self, req: IntelRequest, *, state: StateRepo) -> IntelRun:
        start = time.perf_counter()
        matches = list(req.watchlist_matches)
        if not unknown_web_entities(req):
            return IntelRun(IntelResult(watchlist_matches=matches), False, False, 0, TokenUsage())

        parts = [types.Part.from_text(text=build_input(req))]
        with (
            use_state(state),
            collecting() as tool_matches,
            search.recording() as records,
            _search_budget() as used,
        ):
            # One attempt: a retry could not search again (the budget is spent) and would only
            # produce ungrounded findings. The verdict never waits for this agent.
            run = await self._runner.run(parts, _parse, check_id=req.check_id, attempts=1)
        seen = _listed(matches)
        matches += [m for m in tool_matches if (m.type, m.value) not in seen]
        findings = ground_findings(run.output, records) if run.output else []
        result = IntelResult(watchlist_matches=_dedupe(matches), web_findings=findings)
        intel_run = IntelRun(
            result=result,
            called_model=True,
            failed=run.failed,
            latency_ms=round((time.perf_counter() - start) * 1000),
            tokens=run.tokens,
            searches=len(used),
            error=run.error,
        )
        log.info(
            "intel_investigated",
            check_id=req.check_id,
            agent=AGENT_NAME,
            latency_ms=intel_run.latency_ms,
            tokens_in=run.tokens.in_,
            tokens_out=run.tokens.out,
            searches=len(used),
            findings=[(f.query[:80], f.risk, len(f.sources)) for f in findings],
            failed=run.failed,
        )
        return intel_run


def _parse(text: str) -> IntelFindings:
    return IntelFindings.model_validate(parse_json_object(text))


def _dedupe(matches: list[WatchlistMatch]) -> list[WatchlistMatch]:
    out: dict[tuple[str, str], WatchlistMatch] = {}
    for m in matches:
        out.setdefault((m.type, m.value), m)
    return list(out.values())
