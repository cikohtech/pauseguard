"""Case-File agent (AGENTS_SPEC §6): the analyst's summary of an AMBER/RED check.

    run = await casefile.write(CaseFileRequest(...))
    run.case_file  CaseFile, always valid (a deterministic one if the model failed)

Runs after the customer has their verdict, so it never adds to the customer's wait. Evidence
points are re-anchored on the evidence agent's flags: the model picks and orders them, but every
quote and evidence index in the case file is copied from the evidence analysis, never retyped.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.genai import types
from pydantic import ValidationError

from app.agents._runtime import (
    AgentRunner,
    count_tokens,
    generate_config,
    load_prompt,
    neutralise,
    parse_json_object,
    resolve_model,
)
from app.agents.explainer_agent import TYPOLOGY_LABELS, limit
from app.config import Settings, get_settings
from app.log import get_logger
from app.models.schemas import (
    AnalystAction,
    CaseFile,
    EvidenceAnalysis,
    EvidencePoint,
    FusionResult,
    IntelResult,
    RedFlag,
    TokenUsage,
    Transfer,
    TxnRisk,
)

log = get_logger(__name__)

AGENT_NAME = "casefile_agent"
MAX_TITLE_WORDS = 10
MAX_POINTS = 6


@dataclass
class CaseFileRequest:
    transfer: Transfer
    txn: TxnRisk
    fusion: FusionResult
    evidence: EvidenceAnalysis | None = None
    intel: IntelResult | None = None
    customer_text: str | None = None
    quick_reply: str | None = None
    check_id: str | None = None


@dataclass
class CaseFileRun:
    case_file: CaseFile
    called_model: bool
    failed: bool
    latency_ms: int
    tokens: TokenUsage
    error: str | None = None


def intel_points(intel: IntelResult | None) -> list[str]:
    if not intel:
        return []
    points = [
        f"{m.type.title()} {m.value} on the watchlist, reported {m.reported_count} time(s) "
        f"({m.source.lower().replace('_', ' ')})"
        for m in intel.watchlist_matches
    ]
    points += [f"Web ({f.risk}): {f.query}: {f.finding}" for f in intel.web_findings]
    return points


def fallback_case_file(req: CaseFileRequest) -> CaseFile:
    """A factual case file from the structured results alone (no model)."""
    t, f, ev = req.transfer, req.fusion, req.evidence
    typology = ev.typology_guess if ev else "UNKNOWN"
    label = TYPOLOGY_LABELS[typology][0]
    summary = [f"Automatic case summary unavailable; built from the policy results ({f.verdict})."]
    summary.append("Policy reasons: " + "; ".join(f.reasons) + ".")
    if ev and ev.summary:
        summary.append(f"Evidence summary: {ev.summary}")
    action: AnalystAction = "HOLD" if f.verdict == "RED" or not f.needs_review else "ESCALATE"
    return CaseFile(
        title=limit(f"{label.capitalize()}, {f.verdict}, S${t.amount:,.0f} to new payee", 10, "en"),
        summary=" ".join(summary),
        timeline=[f"Customer started a S${t.amount:,.2f} transfer to {t.payee_name}"],
        evidence_points=[_point(x) for x in (ev.red_flags if ev else [])[:MAX_POINTS]],
        intel_points=intel_points(req.intel),
        recommended_action=action,
        recommended_reason="Recommended by the fallback rules; the model did not write this file.",
        confidence=ev.typology_confidence if ev and typology not in {"NONE", "UNKNOWN"} else 0.5,
    )


def _point(flag: RedFlag) -> EvidencePoint:
    return EvidencePoint(flag=flag.code, quote=flag.quote, evidence_index=flag.evidence_index)


def anchor_points(points: list[EvidencePoint], flags: list[RedFlag]) -> list[EvidencePoint]:
    """The model's choice and order of points, with quotes and indexes copied from the flags."""
    pool = list(flags)
    out = []
    for p in points:
        flag = next((x for x in pool if x.code == p.flag), None)
        if flag:
            pool.remove(flag)
            out.append(_point(flag))
    return (out or [_point(x) for x in flags])[:MAX_POINTS]


def build_input(req: CaseFileRequest) -> str:
    t, ev, f = req.transfer, req.evidence, req.fusion
    lines = [
        "<transfer>",
        f"Payee: {neutralise(t.payee_name)}, account {neutralise(t.account_number)}"
        + (f" ({neutralise(t.bank_name)})" if t.bank_name else ""),
        f"Amount: {t.currency} {t.amount:,.2f}, destination {t.dest_type}",
        f"Transaction risk score: {req.txn.score}",
        *(f"- {r.label} (+{r.points})" for r in req.txn.reasons),
        "</transfer>",
        "<customer_answer>",
        f"Quick reply: {neutralise(req.quick_reply or '(none)')}",
        f"Answer: {neutralise(req.customer_text or '(none)')}",
        "</customer_answer>",
        "<evidence>",
    ]
    if ev:
        lines.append(f"Evidence shared: {'yes' if ev.evidence_present else 'no'}")
        lines.append(f"Typology guess: {ev.typology_guess} ({ev.typology_confidence:.2f})")
        lines.append(f"Summary: {neutralise(ev.summary)}")
        if ev.claimed_sender:
            lines.append(f"Claimed sender: {neutralise(ev.claimed_sender.model_dump_json())}")
        if ev.payment_instruction:
            lines.append(
                f"Payment instruction: {neutralise(ev.payment_instruction.model_dump_json())}"
            )
        lines.append(f"Entities: {neutralise(ev.entities.model_dump_json())}")
        lines += [
            f'- {x.code} ({x.severity}), evidence {x.evidence_index}: "{neutralise(x.quote)}"'
            for x in ev.red_flags
        ]
        if ev.injection_attempt_detected:
            lines.append("Prompt-injection attempt detected in the evidence.")
    else:
        lines.append("(no evidence analysis)")
    lines += ["</evidence>", "<intel>"]
    lines += [f"- {neutralise(p)}" for p in intel_points(req.intel)] or ["(none)"]
    lines += [
        "</intel>",
        "<verdict>",
        f"{f.verdict} ({f.action}){' - needs human review' if f.needs_review else ''}",
        *(f"- {neutralise(r)}" for r in f.reasons),
        "</verdict>",
    ]
    return "\n".join(lines)


def _parse(text: str) -> CaseFile:
    data = parse_json_object(text)
    if isinstance(data.get("confidence"), int | float):
        data["confidence"] = min(1.0, max(0.0, float(data["confidence"])))
    points = []
    for p in data.get("evidence_points") or []:
        try:
            points.append(EvidencePoint.model_validate(p))
        except ValidationError:  # e.g. an unknown flag code: dropped, not a reason to retry
            continue
    data["evidence_points"] = points
    return CaseFile.model_validate(data)


def postprocess(case: CaseFile, req: CaseFileRequest) -> CaseFile:
    flags = req.evidence.red_flags if req.evidence else []
    return case.model_copy(
        update={
            "title": limit(case.title, MAX_TITLE_WORDS, "en"),
            "evidence_points": anchor_points(case.evidence_points, flags),
        }
    )


def build_agent(model: str | BaseLlm | None = None, settings: Settings | None = None) -> LlmAgent:
    settings = settings or get_settings()
    return LlmAgent(
        name=AGENT_NAME,
        description="Writes the fraud analyst's case file for an AMBER or RED check.",
        model=resolve_model(model, settings),
        static_instruction=load_prompt("casefile"),
        output_schema=CaseFile,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=generate_config(settings),
        after_model_callback=count_tokens,
    )


class CaseFileAgent:
    def __init__(self, model: str | BaseLlm | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.export_sdk_env()
        self.agent = build_agent(model, self.settings)
        self._runner = AgentRunner(self.agent)

    async def write(self, req: CaseFileRequest) -> CaseFileRun:
        parts = [types.Part.from_text(text=build_input(req))]
        run = await self._runner.run(parts, _parse, check_id=req.check_id)
        case = postprocess(run.output, req) if run.output else fallback_case_file(req)
        log.info(
            "case_file_written",
            check_id=req.check_id,
            agent=AGENT_NAME,
            latency_ms=run.latency_ms,
            tokens_in=run.tokens.in_,
            tokens_out=run.tokens.out,
            attempts=run.attempts,
            failed=run.failed,
            recommended=case.recommended_action,
        )
        return CaseFileRun(case, True, run.failed, run.latency_ms, run.tokens, run.error)
