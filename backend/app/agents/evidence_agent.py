"""Evidence agent (AGENTS_SPEC §2): Gemini reads the customer's answer and the evidence they
shared (screenshots, PDFs, pasted text) and extracts facts and red flags. It never decides the
verdict; policy/fusion.py does.

    run = await analyse_evidence(EvidenceRequest(...))
    run.analysis   EvidenceAnalysis, always valid (a safe fallback if the model failed)
    run.failed     True when the model gave no valid answer after one retry; the fusion policy
                   then returns AMBER + human review, never GREEN

The model runs as an ADK LlmAgent with `output_schema=EvidenceAnalysis`. We validate its JSON
ourselves (ADK's own output_key validation is not used), retry once, then fall back. After that,
deterministic post-processing merges the prompt-injection pre-scan, drops boxes that are not on
an image, and caps the flags at 6, most severe first.

CLI (local dev):
    python -m app.agents.evidence_agent --file ../data/demo/tan_mas_chat.png --text "..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings, get_settings
from app.log import get_logger
from app.models.schemas import (
    DestType,
    EvidenceAnalysis,
    RedFlag,
    Severity,
    TokenUsage,
    Transfer,
)
from app.security.injection import InjectionHit, scan_all

log = get_logger(__name__)

AGENT_NAME = "evidence_agent"
APP_NAME = "pauseguard"
PROMPT_PATH = Path(__file__).with_name("prompts") / "evidence.md"
MAX_EVIDENCE = 3
MAX_FLAGS = 6
MAX_ATTEMPTS = 2  # the first call plus one retry (CLAUDE.md rule 4)
FALLBACK_SUMMARY = "Automatic evidence analysis failed; a person needs to review this payment."

EvidenceKind = Literal["image", "pdf", "text"]
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}
_SEVERITY_RANK: dict[Severity, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_TAG_BREAKOUT = re.compile(r"<(/?\s*(?:evidence|transfer|customer_answer|system)\b)", re.I)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@dataclass
class EvidenceItem:
    """One piece of evidence: a file (gs:// URI, or a local path in local dev) or pasted text."""

    uri: str | None = None
    text: str | None = None
    mime_type: str | None = None

    def __post_init__(self) -> None:
        if (self.uri is None) == (self.text is None):
            raise ValueError("EvidenceItem needs exactly one of `uri` or `text`.")
        if self.uri and not self.mime_type:
            suffix = Path(self.uri).suffix.lower()
            self.mime_type = _MIME_BY_SUFFIX.get(suffix) or mimetypes.guess_type(self.uri)[0]
        if self.text is not None:
            self.mime_type = "text/plain"

    @property
    def kind(self) -> EvidenceKind:
        if self.mime_type in _IMAGE_TYPES:
            return "image"
        if self.mime_type == "application/pdf":
            return "pdf"
        if self.mime_type == "text/plain":
            return "text"
        raise ValueError(f"Unsupported evidence type {self.mime_type!r} ({self.uri}).")

    @classmethod
    def from_path_or_uri(cls, value: str) -> EvidenceItem:
        """A .txt file becomes pasted text; anything else stays a file reference."""
        if not value.startswith("gs://") and value.lower().endswith(".txt"):
            return cls(text=_safe_local_path(value).read_text(encoding="utf-8"))
        return cls(uri=value)


@dataclass
class EvidenceRequest:
    customer_text: str | None = None
    quick_reply: str | None = None
    items: list[EvidenceItem] = field(default_factory=list)
    transfer: Transfer | None = None
    check_id: str | None = None  # for the log line only

    def __post_init__(self) -> None:
        if len(self.items) > MAX_EVIDENCE:
            raise ValueError(f"At most {MAX_EVIDENCE} evidence items per check.")


@dataclass
class EvidenceRun:
    analysis: EvidenceAnalysis
    failed: bool
    attempts: int
    latency_ms: int
    tokens: TokenUsage
    error: str | None = None
    injection_hits: list[InjectionHit] = field(default_factory=list)


def _safe_local_path(value: str) -> Path:
    """Local files are for local dev only, and only inside the repo (no reading /etc/passwd).
    A relative path is tried from the current directory, then from the repo root."""
    if get_settings().is_cloud:
        raise ValueError("Local evidence paths are not allowed on Cloud Run; use gs:// URIs.")
    path = Path(value)
    candidates = [path] if path.is_absolute() else [Path.cwd() / path, REPO_ROOT / path]
    for candidate in (c.resolve() for c in candidates):
        if not candidate.is_relative_to(REPO_ROOT):
            raise ValueError(f"Evidence path {value!r} is outside the repository.")
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(value)


def _neutralise(text: str) -> str:
    """Untrusted text cannot close our delimiters: '</evidence>' becomes '‹/evidence>'."""
    return _TAG_BREAKOUT.sub(r"‹\1", text)


def _transfer_block(t: Transfer) -> str:
    bank = f" ({t.bank_name})" if t.bank_name else ""
    lines = [
        f"Payee: {t.payee_name}",
        f"Account: {t.account_number}{bank}",
        f"Amount: {t.currency} {t.amount:,.2f}",
        f"Destination type: {t.dest_type}",
    ]
    if t.note:
        lines.append(f"Note: {_neutralise(t.note)}")
    return "<transfer>\n" + "\n".join(lines) + "\n</transfer>"


def build_parts(req: EvidenceRequest) -> list[types.Part]:
    """The user turn: transfer, the customer's answer, then each evidence item in delimiters."""
    head = []
    if req.transfer:
        head.append(_transfer_block(req.transfer))
    answer = [
        f"Quick reply: {_neutralise(req.quick_reply)}" if req.quick_reply else "",
        f"Answer: {_neutralise(req.customer_text)}" if req.customer_text else "",
    ]
    head.append(
        "<customer_answer>\n"
        + ("\n".join(a for a in answer if a) or "(no answer)")
        + "\n</customer_answer>"
    )
    if not req.items:
        head.append("No evidence was shared.")
    parts = [types.Part.from_text(text="\n".join(head))]

    for i, item in enumerate(req.items):
        kind = item.kind
        if kind == "text":
            body = _neutralise(item.text or "")
            parts.append(
                types.Part.from_text(
                    text=f'<evidence index="{i}" type="text">\n{body}\n</evidence>'
                )
            )
            continue
        parts.append(types.Part.from_text(text=f'<evidence index="{i}" type="{kind}">'))
        assert item.uri and item.mime_type
        if item.uri.startswith("gs://"):
            parts.append(types.Part.from_uri(file_uri=item.uri, mime_type=item.mime_type))
        else:
            data = _safe_local_path(item.uri).read_bytes()
            parts.append(types.Part.from_bytes(data=data, mime_type=item.mime_type))
        parts.append(types.Part.from_text(text="</evidence>"))
    return parts


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@lru_cache
def load_prompt() -> str:
    """The prompt file without its leading HTML comment (the changelog)."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def build_agent(model: str | BaseLlm | None = None, settings: Settings | None = None) -> LlmAgent:
    settings = settings or get_settings()
    return LlmAgent(
        name=AGENT_NAME,
        description="Extracts facts and scam red flags from the evidence behind a payment.",
        model=model or settings.gemini_model,
        static_instruction=load_prompt(),
        output_schema=EvidenceAnalysis,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(settings.gemini_thinking_level)
            ),
        ),
    )


class EvidenceAgent:
    """One ADK Runner around the evidence LlmAgent; every call gets a fresh session."""

    def __init__(self, model: str | BaseLlm | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.export_sdk_env()
        self.agent = build_agent(model, self.settings)
        self.sessions = InMemorySessionService()
        self.runner = Runner(app_name=APP_NAME, agent=self.agent, session_service=self.sessions)

    async def _call(self, parts: list[types.Part]) -> tuple[str, TokenUsage]:
        """One model call: the final text and its token usage."""
        user_id = "pauseguard"
        session = await self.sessions.create_session(app_name=APP_NAME, user_id=user_id)
        text, tokens = "", TokenUsage()
        try:
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=types.Content(role="user", parts=parts),
            ):
                if event.error_code:
                    raise RuntimeError(f"model error {event.error_code}: {event.error_message}")
                if u := event.usage_metadata:
                    tokens.in_ += u.prompt_token_count or 0
                    tokens.out += (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
                if event.author == AGENT_NAME and event.is_final_response() and event.content:
                    text = "".join(
                        p.text for p in event.content.parts or [] if p.text and not p.thought
                    )
        finally:
            await self.sessions.delete_session(
                app_name=APP_NAME, user_id=user_id, session_id=session.id
            )
        return text, tokens

    async def analyse(self, req: EvidenceRequest) -> EvidenceRun:
        start = time.perf_counter()
        tokens = TokenUsage()
        analysis: EvidenceAnalysis | None = None
        error: str | None = None
        attempts = 0
        try:
            parts = build_parts(req)
        except (ValueError, OSError) as e:  # unreadable evidence: no model call, safe fallback
            parts, error = [], f"evidence unreadable: {_short(e)}"
        for attempt in range(1, MAX_ATTEMPTS + 1 if parts else 1):
            attempts = attempt
            try:
                text, used = await self._call(parts)
                tokens.in_ += used.in_
                tokens.out += used.out
                analysis = parse_analysis(text)
                break
            except (ValueError, ValidationError) as e:  # bad JSON or schema
                error = f"invalid output: {_short(e)}"
            except Exception as e:  # model or network error: retried, then the fallback
                error = f"{type(e).__name__}: {_short(e)}"
            log.warning(
                "evidence_attempt_failed", check_id=req.check_id, attempt=attempt, error=error
            )

        failed = analysis is None
        hits = prescan(req, analysis)
        final = postprocess(analysis or fallback_analysis(req), req, hits)
        run = EvidenceRun(
            analysis=final,
            failed=failed,
            attempts=attempts,
            latency_ms=round((time.perf_counter() - start) * 1000),
            tokens=tokens,
            error=error if failed else None,
            injection_hits=hits,
        )
        log.info(
            "evidence_analysed",
            check_id=req.check_id,
            agent=AGENT_NAME,
            latency_ms=run.latency_ms,
            tokens_in=tokens.in_,
            tokens_out=tokens.out,
            attempts=attempts,
            failed=failed,
            typology=final.typology_guess,
            confidence=final.typology_confidence,
            flags=[f.code for f in final.red_flags],
            injection=final.injection_attempt_detected,
            evidence=[i.kind for i in req.items],
        )
        return run


@lru_cache
def default_agent() -> EvidenceAgent:
    return EvidenceAgent()


async def analyse_evidence(
    req: EvidenceRequest, *, agent: EvidenceAgent | None = None
) -> EvidenceRun:
    return await (agent or default_agent()).analyse(req)


def _short(e: Exception, limit: int = 300) -> str:
    return str(e).replace("\n", " ")[:limit]


# ---------------------------------------------------------------------------
# Parsing, fallback and post-processing (deterministic)
# ---------------------------------------------------------------------------


def _clean_box(box: Any) -> list[int] | None:
    """Gemini sometimes returns floats; anything that isn't 4 numbers is dropped."""
    if not isinstance(box, list) or len(box) != 4:
        return None
    if not all(isinstance(n, int | float) and not isinstance(n, bool) for n in box):
        return None
    return [round(n) for n in box]


def parse_analysis(text: str) -> EvidenceAnalysis:
    """Model text -> EvidenceAnalysis. A flag with an unknown code is dropped, not fatal;
    anything else that doesn't fit the schema raises (and is retried)."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    if not raw:
        raise ValueError("empty model output")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    flags = []
    for f in data.get("red_flags") or []:
        if isinstance(f, dict):
            f = {**f, "box_2d": _clean_box(f.get("box_2d"))}
        try:
            flags.append(RedFlag.model_validate(f))
        except ValidationError:
            log.warning("evidence_flag_dropped", flag=str(f)[:200])
    data["red_flags"] = _rank(flags)
    return EvidenceAnalysis.model_validate(data)


def fallback_analysis(req: EvidenceRequest) -> EvidenceAnalysis:
    """The safe default when the model fails: no verdict information, flagged as unknown."""
    return EvidenceAnalysis(
        evidence_present=bool(req.items),
        summary=FALLBACK_SUMMARY,
        typology_guess="UNKNOWN",
        typology_confidence=0.0,
    )


def prescan(req: EvidenceRequest, analysis: EvidenceAnalysis | None) -> list[InjectionHit]:
    """Regex pre-scan of everything we can read as text: the customer's answer, pasted text,
    and the model's verbatim quotes (images and PDFs are read through the model's quotes)."""
    texts: list[tuple[str, str | None]] = [
        ("customer_answer", req.customer_text),
        ("quick_reply", req.quick_reply),
        *((f"evidence[{i}]", it.text) for i, it in enumerate(req.items) if it.text is not None),
    ]
    if analysis:
        texts += [(f"quote:{f.evidence_index}", f.quote) for f in analysis.red_flags]
        if analysis.payment_instruction:
            texts.append(("payment_reason", analysis.payment_instruction.reason_given))
    return scan_all(texts)


def _rank(flags: list[RedFlag]) -> list[RedFlag]:
    """Most severe first (stable), duplicates removed, at most MAX_FLAGS."""
    seen: set[tuple[str, str]] = set()
    unique = []
    for f in sorted(flags, key=lambda f: _SEVERITY_RANK[f.severity]):
        key = (f.code, f.quote.strip())
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique[:MAX_FLAGS]


def _injection_flag(hits: list[InjectionHit]) -> RedFlag:
    """COACHING_TO_LIE for an injection the pre-scan found, or the model saw but didn't flag."""
    if not hits:
        return RedFlag(
            code="COACHING_TO_LIE", severity="HIGH", quote="(instructions aimed at the reviewer)"
        )
    hit = hits[0]
    m = re.fullmatch(r"(?:evidence\[|quote:)(\d+)\]?", hit.source)
    index = int(m.group(1)) if m else None
    return RedFlag(code="COACHING_TO_LIE", severity="HIGH", quote=hit.context, evidence_index=index)


def postprocess(
    analysis: EvidenceAnalysis, req: EvidenceRequest, hits: list[InjectionHit]
) -> EvidenceAnalysis:
    """Deterministic rules applied to every result, model or fallback."""
    flags: list[RedFlag] = []
    for f in analysis.red_flags:
        if f.code == "WATCHLIST_MATCH":  # only the watchlist tool may set this
            continue
        index = f.evidence_index
        if index is not None and not 0 <= index < len(req.items):
            index = None
        on_image = index is not None and req.items[index].kind == "image"
        flags.append(
            f.model_copy(update={"evidence_index": index, "box_2d": f.box_2d if on_image else None})
        )

    injection = analysis.injection_attempt_detected or bool(hits)
    if injection and not any(f.code == "COACHING_TO_LIE" for f in flags):
        flags.insert(0, _injection_flag(hits))

    return analysis.model_copy(
        update={
            "evidence_present": bool(req.items),
            "red_flags": _rank(flags),
            "injection_attempt_detected": injection,
        }
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.agents.evidence_agent",
        description="Run the evidence agent on local files or gs:// URIs and print the JSON.",
    )
    p.add_argument("--file", action="append", default=[], help="image/PDF/.txt (up to 3)")
    p.add_argument("--text", help="the customer's answer")
    p.add_argument("--quick-reply", help="the quick reply the customer tapped")
    p.add_argument("--paste", action="append", default=[], help="pasted text evidence")
    p.add_argument("--payee", help="transfer payee name")
    p.add_argument("--account", default="(not given)", help="transfer account number")
    p.add_argument("--bank", help="transfer bank name")
    p.add_argument("--amount", type=float, help="transfer amount (SGD)")
    p.add_argument("--dest-type", default="LOCAL_BANK", help="LOCAL_BANK, OVERSEAS, ...")
    p.add_argument("--note", help="transfer note")
    return p.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    items = [EvidenceItem.from_path_or_uri(f) for f in args.file]
    items += [EvidenceItem(text=t) for t in args.paste]
    transfer = None
    if args.payee and args.amount:
        dest: DestType = args.dest_type
        transfer = Transfer(
            payee_name=args.payee,
            account_number=args.account,
            bank_name=args.bank,
            amount=args.amount,
            dest_type=dest,
            note=args.note,
        )
    req = EvidenceRequest(
        customer_text=args.text,
        quick_reply=args.quick_reply,
        items=items,
        transfer=transfer,
        check_id=f"cli_{uuid.uuid4().hex[:8]}",
    )
    run = await analyse_evidence(req)
    print(run.analysis.model_dump_json(indent=2))
    print(
        f"# latency {run.latency_ms} ms · tokens in {run.tokens.in_} out {run.tokens.out} · "
        f"attempts {run.attempts} · failed {run.failed}" + (f" ({run.error})" if run.error else ""),
        file=sys.stderr,
    )
    return 1 if run.failed else 0


if __name__ == "__main__":
    from app.log import configure_logging

    configure_logging(get_settings().log_level, stream=sys.stderr)
    raise SystemExit(asyncio.run(_main()))
