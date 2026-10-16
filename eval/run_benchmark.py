"""Benchmark runner (EVAL_PLAN §5): rules only (B0), one Gemini prompt (B1) and PauseGuard on the
held-out test split. `make eval` runs it locally, then eval/report.py.

    uv --directory backend run --group eval python ../eval/run_benchmark.py --local
    uv --directory backend run --group eval python ../eval/run_benchmark.py --api https://<run.app>
    ... --split dev --ids ev_0002 ev_0005 --systems b0,b1,pauseguard --concurrency 4

Systems (all see the same case; the first three are the report's main table):
  b0             rules_only_verdict(transaction score): RED >= 70, AMBER >= 40      (no model)
  b1             one Gemini call with every input returns the verdict (baselines/single_prompt.py)
  pauseguard     the product: GREEN fast path for low scores, else the check-in, the agents and
                 the deterministic fusion policy
  pg_always      ablation (--local only): the fast path off, every case gets the check-in
  pg_noevidence  ablation (--local only): the customer's answer only, the evidence left out

Targets:
  --local   The orchestrator in this process (EVAL_PLAN: "or the in-process orchestrator"). The
            transactions come from a fresh SQLite database built by the synthetic generator with a
            pinned end date and scored at a pinned "now" (SEED_END_DATE, AS_OF below), so every
            transaction score, and so B0, is the same on every run. State is in memory (seeded
            watchlist), evidence is read from data/eval/.
  --api     The deployed API, as the customer app calls it: POST /checks, sign + PUT the evidence,
            POST /checks/{id}/messages. It sends the admin token (ADMIN_TOKEN, else .env) with
            `X-PauseGuard-Eval: true`, so the checks stay out of /metrics, and calls
            POST /admin/purge-eval at the end so the analyst console is left clean (--keep: don't).
            The transaction score is the deployed one (BigQuery data, scored at call time); B0 and
            B1 use that same score, so the three systems always share their inputs.

Raw rows: eval/results/<stamp>_<target>_<split>_<system>.jsonl, one per case, each with the model
ID, git SHA and timestamps. `make eval` checks the test split's hash first (make eval-verify).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baselines.single_prompt import default_client, run_single_prompt  # noqa: E402
from metrics import (  # noqa: E402
    ABLATION_SYSTEMS,
    MAIN_SYSTEMS,
    MAX_TIMEOUT_SHARE,
    summary_table,
    timeout_share,
)

from app.agents.casefile_agent import (  # noqa: E402
    CaseFileAgent,
    CaseFileRequest,
    CaseFileRun,
    fallback_case_file,
)
from app.agents.evidence_agent import EvidenceItem, EvidenceRequest  # noqa: E402
from app.agents.intel_agent import IntelAgent, IntelRequest, IntelRun  # noqa: E402
from app.agents.orchestrator import QUICK_REPLIES, CheckOutcome, Orchestrator  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.data.memory_repo import MemoryStateRepo  # noqa: E402
from app.data.seed import generate, load_sqlite, watchlist_entries  # noqa: E402
from app.data.sqlite_repo import SqliteTransactionRepo  # noqa: E402
from app.models.schemas import (  # noqa: E402
    CheckMessageRequest,
    CreateCheckRequest,
    IntelResult,
    TokenUsage,
    Transfer,
    TxnRisk,
)
from app.tools.txn_features import compute_txn_risk, rules_only_verdict  # noqa: E402
from app.tools.watchlist import lookup_entities  # noqa: E402

CASES = ROOT / "data" / "eval" / "cases.jsonl"
RESULTS = ROOT / "eval" / "results"
SGT = timezone(timedelta(hours=8))
SEED = 42
SEED_END_DATE = date(2026, 10, 10)  # the synthetic history the eval set was built against
AS_OF = datetime(2026, 10, 10, 10, 0, tzinfo=SGT)  # a weekday morning, 10 h after it ends
ALL_SYSTEMS = MAIN_SYSTEMS + ABLATION_SYSTEMS
# Pre-flight (DECISIONS 2026-10-15): a one-word reply normally takes 1.5-2.5 s on the global
# endpoint. 3 pings at a 5 s median let a degraded window through on 15 Oct, hence 5 pings.
PREFLIGHT_PINGS = 5
PREFLIGHT_MAX_MEDIAN_MS = 3000
PREFLIGHT_SLOW_MS, PREFLIGHT_MAX_SLOW = 10_000, 1  # at most one ping above 10 s
CASEFILE_WAIT_SECONDS = 45.0  # --api: wait this long for the case file (and the final tokens)
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf"}


# --- cases -----------------------------------------------------------------------------------


@dataclass
class Case:
    raw: dict[str, Any]
    age: int | None = None

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def customer_id(self) -> str:
        return str(self.raw["transfer"]["customer_id"])

    @property
    def language(self) -> str:
        return str(self.raw["language"])

    @property
    def transfer(self) -> Transfer:
        drop = {"customer_id", "is_new_payee"}
        return Transfer(**{k: v for k, v in self.raw["transfer"].items() if k not in drop})

    @property
    def evidence_type(self) -> str:
        """image | pdf | text | none (one item at most per case)."""
        return next((str(e["type"]) for e in self.raw["evidence"]), "none")

    @property
    def files(self) -> list[str]:
        return [e["path"] for e in self.raw["evidence"] if e["type"] in ("image", "pdf")]

    @property
    def pasted_text(self) -> str | None:
        return next((e["text"] for e in self.raw["evidence"] if e["type"] == "text"), None)

    @property
    def quick_reply(self) -> str | None:
        """The chip the customer taps, in the check's language (the eval set stores English)."""
        qr = self.raw.get("quick_reply")
        if not qr:
            return None
        lang = "zh" if self.language == "zh" else "en"
        return QUICK_REPLIES[lang][QUICK_REPLIES["en"].index(qr)]

    def create_request(self) -> CreateCheckRequest:
        return CreateCheckRequest(
            customer_id=self.customer_id,
            transfer=self.transfer,
            language=self.language,  # type: ignore[arg-type]
        )

    def message(
        self, evidence_uris: list[str], *, with_evidence: bool = True
    ) -> CheckMessageRequest:
        return CheckMessageRequest(
            text=self.raw["customer_answer"],
            quick_reply=self.quick_reply,
            evidence_uris=evidence_uris if with_evidence else [],
            pasted_text=self.pasted_text if with_evidence else None,
        )

    def evidence_request(self, check_id: str) -> EvidenceRequest:
        """B1's input: the same answer and evidence the evidence agent gets."""
        items = [EvidenceItem(uri=p) for p in self.files]
        if self.pasted_text:
            items.append(EvidenceItem(text=self.pasted_text))
        return EvidenceRequest(
            customer_text=self.raw["customer_answer"],
            quick_reply=self.quick_reply,
            items=items,
            transfer=self.transfer,
            check_id=check_id,
        )

    def base_row(self) -> dict[str, Any]:
        r = self.raw
        return {
            "id": self.id,
            "split": r["split"],
            "label": r["label"],
            "typology": r["typology"],
            "scenario": r["scenario"],
            "language": r["language"],
            "difficulty": r["difficulty"],
            "injection": r["injection"],
            "evidence_type": self.evidence_type,
            "customer_id": self.customer_id,
            "age": self.age,
            "amount": r["transfer"]["amount"],
            "dest_type": r["transfer"]["dest_type"],
        }


def load_cases(split: str, ids: list[str] | None) -> list[Case]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    cases = [Case(r) for r in rows if split == "all" or r["split"] == split]
    if ids:
        cases = [c for c in cases if c.id in set(ids)]
        missing = set(ids) - {c.id for c in cases}
        if missing:
            raise SystemExit(f"Not in the {split} split: {sorted(missing)}")
    return cases


# --- the transaction step shared by every system ----------------------------------------------


@dataclass
class TxnStep:
    """The case's transaction risk, as POST /checks computed it; B0 and B1 read it from here."""

    risk: TxnRisk
    ms: int
    check_id: str | None = None  # --api: the check the pauseguard system continues
    started: dict[str, Any] | None = None  # --api: the POST /checks response


def txn_fields(risk: TxnRisk) -> dict[str, Any]:
    return {"txn_score": risk.score, "txn_reasons": [r.code for r in risk.reasons]}


def b0_row(case: Case, step: TxnStep) -> dict[str, Any]:
    verdict = rules_only_verdict(step.risk.score)
    return {
        **case.base_row(),
        **txn_fields(step.risk),
        "verdict": verdict,
        "typology_pred": None,
        "confidence": None,
        "needs_review": False,
        "failed": False,
        "fast_path": False,
        "e2e_ms": step.ms,
        "answer_ms": None,
        "latency_ms": {"txn": step.ms},
        "tokens": {"in": 0, "out": 0},
    }


async def b1_row(case: Case, step: TxnStep, settings: Settings) -> dict[str, Any]:
    run = await run_single_prompt(case.evidence_request(f"b1_{case.id}"), step.risk, settings)
    a = run.answer
    return {
        **case.base_row(),
        **txn_fields(step.risk),
        "verdict": a.verdict,
        "typology_pred": a.typology,
        "confidence": a.confidence,
        "reason": a.reason,
        "needs_review": run.failed,
        "failed": run.failed,
        "error": run.error,
        "attempts": run.attempts,
        "fast_path": False,
        "e2e_ms": step.ms + run.latency_ms,
        "answer_ms": run.latency_ms,
        "latency_ms": {"txn": step.ms, "model": run.latency_ms},
        "tokens": {"in": run.tokens_in, "out": run.tokens_out},
    }


def outcome_row(
    case: Case, outcome: CheckOutcome, start_ms: int, grounding_queries: int
) -> dict[str, Any]:
    """A PauseGuard row from an in-process run (Orchestrator.run_check)."""
    risk = outcome.started.txn_risk or TxnRisk(score=0)
    a = outcome.analysis
    msg = outcome.customer_message
    row: dict[str, Any] = {
        **case.base_row(),
        **txn_fields(risk),
        "verdict": outcome.verdict,
        "fast_path": a is None,
        "message": msg.model_dump(mode="json") if msg else None,
    }
    if a is None:
        return row | {
            "typology_pred": None,
            "confidence": None,
            "needs_review": False,
            "failed": False,
            "e2e_ms": start_ms,
            "answer_ms": None,
            "latency_ms": {"txn": start_ms},
            "tokens": {"in": 0, "out": 0},
            "reasons": [f"GREEN fast path: transaction score {risk.score}, no check-in"],
        }
    r = a.response
    evidence_failed = a.evidence is None or a.evidence.failed  # None: it timed out
    latency = a.latency.model_dump(exclude_none=True)
    return row | {
        "typology_pred": r.typology,
        "confidence": r.confidence,
        "needs_review": r.needs_review,
        "failed": r.needs_review,
        "evidence_failed": evidence_failed,
        "top_flags": [f.code for f in r.top_flags],
        "reasons": a.fusion.reasons,
        "case_id": r.case_id,
        "e2e_ms": start_ms + (a.latency.total or 0),
        "answer_ms": a.latency.total,
        "verdict_ms": a.latency.verdict,
        "pipeline_ms": a.pipeline_ms,
        "latency_ms": latency,
        "tokens": {
            "in": sum(t.in_ for t in a.tokens.values()),
            "out": sum(t.out for t in a.tokens.values()),
        },
        "tokens_by_agent": {k: {"in": v.in_, "out": v.out} for k, v in a.tokens.items()},
        "grounding_queries": grounding_queries,
        "case_file": a.case_file.model_dump(mode="json") if a.case_file else None,
    }


# --- --local ------------------------------------------------------------------------------------


class MeteredIntel(IntelAgent):
    """The Scam-Intel agent, unchanged, plus a record of each check's Google Search queries."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings=settings)
        self.queries: dict[str, int] = {}

    async def investigate(self, req: IntelRequest, *, state: Any) -> IntelRun:
        run = await super().investigate(req, state=state)
        self.queries[req.check_id or ""] = run.grounding_queries
        return run


class NoCaseFile(CaseFileAgent):
    """Ablations only: the deterministic case file, no model call. The case file and the web
    search run after the verdict and fusion never reads them, so leaving them out of an
    ablation changes no verdict; it only saves quota and time."""

    async def write(self, req: CaseFileRequest) -> CaseFileRun:
        return CaseFileRun(fallback_case_file(req), False, False, 0, TokenUsage())


class NoWebSearch(MeteredIntel):
    """Ablations only: keep the watchlist matches, skip the web search (see NoCaseFile)."""

    async def investigate(self, req: IntelRequest, *, state: Any) -> IntelRun:
        result = IntelResult(watchlist_matches=list(req.watchlist_matches))
        return IntelRun(result, False, False, 0, TokenUsage())


class LocalTarget:
    name = "local"

    def __init__(self, settings: Settings, workdir: Path) -> None:
        self.settings = settings
        generate(SEED, SEED_END_DATE, out=workdir)
        load_sqlite(workdir / "bench.db", seed_dir=workdir)
        self.txn_repo = SqliteTransactionRepo(workdir / "bench.db")

    async def state(self) -> MemoryStateRepo:
        state = MemoryStateRepo()
        for e in watchlist_entries():
            await state.put_watchlist(e)
        return state

    def age(self, customer_id: str) -> int | None:
        c = self.txn_repo.get_customer(customer_id)
        return c.age if c else None

    async def txn(self, case: Case, state: MemoryStateRepo) -> TxnStep:
        t = time.perf_counter()
        transfer = case.transfer
        hit = bool(await lookup_entities(state, accounts=[transfer.account_number]))
        risk = await asyncio.to_thread(
            compute_txn_risk,
            case.customer_id,
            transfer,
            repo=self.txn_repo,
            watchlist_hit=hit,
            as_of=AS_OF,
        )
        return TxnStep(risk, _ms(t))

    async def orchestrator(self, system: str) -> tuple[Orchestrator, MeteredIntel]:
        settings = self.settings
        if system == "pg_always":
            settings = settings.model_copy(update={"txn_green_fast_path_below": 0})
        ablation = system in ABLATION_SYSTEMS
        intel = NoWebSearch(settings) if ablation else MeteredIntel(settings)
        orch = Orchestrator(
            txn_repo=self.txn_repo,
            state=await self.state(),
            settings=settings,
            intel=intel,
            casefile=NoCaseFile(settings=settings) if ablation else None,
        )
        return orch, intel

    async def pauseguard(
        self, case: Case, orch: Orchestrator, intel: MeteredIntel, system: str
    ) -> dict[str, Any]:
        t = time.perf_counter()
        started = await orch.start(case.create_request(), as_of=AS_OF, is_eval=True)
        start_ms = _ms(t)
        outcome = CheckOutcome(started)
        if started.status == "CHECKIN":
            msg = case.message(case.files, with_evidence=system != "pg_noevidence")
            outcome.analysis = await orch.analyse(started.check_id, msg)
        queries = intel.queries.pop(started.check_id, 0)
        return outcome_row(case, outcome, start_ms, queries)


# --- --api --------------------------------------------------------------------------------------


class ApiTarget:
    name = "api"

    def __init__(self, base: str, token: str, local: LocalTarget) -> None:
        import httpx

        self.base = base.rstrip("/")
        self.local = local  # customer ages only
        headers = {"X-Admin-Token": token, "X-PauseGuard-Eval": "true"}
        self.http = httpx.AsyncClient(base_url=f"{self.base}/api/v1", headers=headers, timeout=90)

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        """JSON request with backoff on 429/503 (5 tries); other errors raise."""
        for attempt in range(5):
            r = await self.http.request(method, path, **kw)
            if r.status_code in (429, 503) and attempt < 4:
                await asyncio.sleep(2**attempt + 0.5)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("unreachable")

    async def txn(self, case: Case) -> TxnStep:
        t = time.perf_counter()
        started = await self.request("POST", "/checks", json=case.create_request().model_dump())
        risk = TxnRisk.model_validate(started["txn_risk"])
        return TxnStep(risk, _ms(t), started["check_id"], started)

    async def upload(self, check_id: str, path: str) -> str:
        file = ROOT / path
        signed = await self.request(
            "POST",
            "/uploads/sign",
            json={"check_id": check_id, "filename": file.name, "content_type": MIME[file.suffix]},
        )
        put = await self.http.put(
            signed["upload_url"], content=file.read_bytes(), headers=signed["headers"]
        )
        put.raise_for_status()
        return str(signed["gcs_uri"])

    async def pauseguard(self, case: Case, step: TxnStep) -> dict[str, Any]:
        assert step.started is not None and step.check_id
        started = step.started
        row: dict[str, Any] = {
            **case.base_row(),
            **txn_fields(step.risk),
            "check_id": step.check_id,
        }
        if started["status"] == "DONE":  # the GREEN fast path
            return row | {
                "verdict": started["verdict"],
                "fast_path": True,
                "typology_pred": None,
                "confidence": None,
                "needs_review": False,
                "failed": False,
                "e2e_ms": step.ms,
                "answer_ms": None,
                "latency_ms": {"txn": step.ms},
                "tokens": {"in": 0, "out": 0},
                "message": started.get("customer_message"),
            }
        uris = [await self.upload(step.check_id, p) for p in case.files]
        t = time.perf_counter()
        res = await self.request(
            "POST",
            f"/checks/{step.check_id}/messages",
            json=case.message(uris).model_dump(exclude_none=True),
        )
        wall = _ms(t)
        check = await self.final_check(step.check_id, bool(res.get("case_id")))
        lat = res.get("latency_ms") or {}
        fusion = check.get("fusion") or {}
        return row | {
            "verdict": res["verdict"],
            "fast_path": False,
            "typology_pred": res.get("typology"),
            "confidence": res.get("confidence"),
            "needs_review": res.get("needs_review", False),
            "failed": res.get("needs_review", False),
            "top_flags": [f["code"] for f in res.get("top_flags", [])],
            "reasons": fusion.get("reasons"),
            "case_id": res.get("case_id"),
            "e2e_ms": step.ms + wall,
            "answer_ms": lat.get("total"),
            "answer_wall_ms": wall,
            "verdict_ms": lat.get("verdict"),
            "latency_ms": (check.get("latency_ms") or lat),
            "tokens": check.get("tokens") or {"in": 0, "out": 0},
            "message": res.get("customer_message"),
        }

    async def final_check(self, check_id: str, has_case: bool) -> dict[str, Any]:
        """The check after the analyst-facing part (case file + web search), for the tokens."""
        deadline = time.perf_counter() + (CASEFILE_WAIT_SECONDS if has_case else 0)
        while True:
            check: dict[str, Any] = await self.request("GET", f"/checks/{check_id}")
            done = not has_case or (check.get("latency_ms") or {}).get("casefile") is not None
            if done or time.perf_counter() > deadline:
                return check
            await asyncio.sleep(1.5)

    async def purge(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.request("POST", "/admin/purge-eval")
        return result

    async def close(self) -> None:
        await self.http.aclose()


# --- run -----------------------------------------------------------------------------------------


@dataclass
class Run:
    target: str
    split: str
    systems: list[str]
    settings: Settings
    keep: bool = False  # --api: leave the benchmark checks in Firestore
    preflight: dict[str, Any] = field(default_factory=dict)
    stamp: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%dT%H%MZ"))
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def meta(self, api: str | None) -> dict[str, Any]:
        return {
            "run": f"{self.stamp}_{self.target}_{self.split}",
            "target": self.target,
            "api": api,
            "model": self.settings.gemini_model,
            "thinking": self.settings.gemini_thinking_level,
            "media_resolution": self.settings.gemini_media_resolution,
            "agent_timeout_s": self.settings.agent_timeout_seconds,
            # The GREEN fast path's rule; the deployed API's setting isn't visible from here.
            "checkin_every_new_payee": (
                self.settings.checkin_every_new_payee if self.target == "local" else None
            ),
            "git_sha": git_sha(),
            "as_of": AS_OF.isoformat() if self.target == "local" else None,
            "seed_end_date": SEED_END_DATE.isoformat() if self.target == "local" else None,
            "preflight": self.preflight,
        }

    def write(self, api: str | None) -> list[Path]:
        RESULTS.mkdir(parents=True, exist_ok=True)
        meta, paths = self.meta(api), []
        for system, rows in self.rows.items():
            path = RESULTS / f"{self.stamp}_{self.target}_{self.split}_{system}.jsonl"
            with path.open("w", encoding="utf-8") as fh:
                for row in sorted(rows, key=lambda r: r["id"]):
                    full = {"system": system, **meta, **row}
                    fh.write(json.dumps(full, ensure_ascii=False, default=str) + "\n")
            paths.append(path)
        return paths


async def gather_limited[T](
    items: list[Case], fn: Callable[[Case], Awaitable[T]], concurrency: int, label: str
) -> list[T]:
    sem, done = asyncio.Semaphore(concurrency), 0
    t0 = time.perf_counter()

    async def one(case: Case) -> T:
        nonlocal done
        async with sem:
            result = await fn(case)
        done += 1
        if done % 10 == 0 or done == len(items):
            print(f"  {label}: {done}/{len(items)} ({time.perf_counter() - t0:.0f} s)", flush=True)
        return result

    return await asyncio.gather(*(one(c) for c in items))


async def run_local(run: Run, cases: list[Case], concurrency: int) -> None:
    with tempfile.TemporaryDirectory(prefix="pauseguard-bench-") as tmp:
        target = LocalTarget(run.settings, Path(tmp))
        for c in cases:
            c.age = target.age(c.customer_id)
        state = await target.state()
        steps = {c.id: await target.txn(c, state) for c in cases}
        if "b0" in run.systems:
            run.rows["b0"] = [b0_row(c, steps[c.id]) for c in cases]
        if "b1" in run.systems:
            run.rows["b1"] = await gather_limited(
                cases, lambda c: b1_row(c, steps[c.id], run.settings), concurrency, "b1"
            )
        for system in [s for s in run.systems if s in ("pauseguard", *ABLATION_SYSTEMS)]:
            orch, intel = await target.orchestrator(system)
            run.rows[system] = await gather_limited(
                cases,
                lambda c, o=orch, i=intel, s=system: target.pauseguard(c, o, i, s),  # type: ignore[misc]
                concurrency,
                system,
            )


async def run_api(run: Run, cases: list[Case], concurrency: int, api: ApiTarget) -> dict[str, Any]:
    for c in cases:
        c.age = api.local.age(c.customer_id)
    try:
        steps: dict[str, TxnStep] = {}

        async def pauseguard(case: Case) -> dict[str, Any]:
            steps[case.id] = step = await api.txn(case)
            return await api.pauseguard(case, step)

        # The product first: its POST /checks gives every case the deployed transaction score.
        run.rows["pauseguard"] = await gather_limited(cases, pauseguard, concurrency, "pauseguard")
        if "b0" in run.systems:
            run.rows["b0"] = [b0_row(c, steps[c.id]) for c in cases]
        if "b1" in run.systems:
            run.rows["b1"] = await gather_limited(
                cases, lambda c: b1_row(c, steps[c.id], run.settings), concurrency, "b1"
            )
        return {} if run.keep else await api.purge()
    finally:
        await api.close()


async def preflight(settings: Settings) -> dict[str, Any]:
    """Time a few one-word Gemini replies. The global endpoint sometimes takes 20-50 s for
    these (seen on 11 and 15 Oct); a benchmark run then measures the outage, not the system."""
    from google.genai import types

    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel("LOW"))
    )
    times: list[int] = []
    for _ in range(PREFLIGHT_PINGS):
        t = time.perf_counter()
        try:
            await asyncio.wait_for(
                default_client().aio.models.generate_content(
                    model=settings.gemini_model, contents="Reply with OK.", config=config
                ),
                60,
            )
            times.append(_ms(t))
        except Exception:
            times.append(60_000)
    median = sorted(times)[len(times) // 2]
    slow = sum(t > PREFLIGHT_SLOW_MS for t in times)
    ok = median <= PREFLIGHT_MAX_MEDIAN_MS and slow <= PREFLIGHT_MAX_SLOW
    return {"pings_ms": times, "median_ms": median, "ok": ok}


def git_sha() -> str:
    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return out.stdout.strip()

    sha = git("rev-parse", "--short=12", "HEAD") or "unknown"
    return sha + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")


def secs_short(ms: int) -> str:
    return f"{ms / 1000:.1f} s"


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--local", action="store_true", help="in-process orchestrator")
    where.add_argument("--api", metavar="URL", help="a running API (the deployed Cloud Run URL)")
    p.add_argument("--split", default="test", choices=["test", "dev", "all"])
    p.add_argument("--ids", nargs="*", help="only these cases")
    p.add_argument("--systems", default=None, help=f"comma-separated, from {','.join(ALL_SYSTEMS)}")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--keep", action="store_true", help="--api: don't purge the benchmark checks")
    p.add_argument("--no-write", action="store_true", help="print only (smoke runs)")
    p.add_argument("--force", action="store_true", help="run even if the pre-flight check fails")
    args = p.parse_args(argv)

    default = ",".join(ALL_SYSTEMS if args.local else MAIN_SYSTEMS)
    systems = [s.strip() for s in (args.systems or default).split(",") if s.strip()]
    unknown = set(systems) - set(ALL_SYSTEMS)
    if unknown:
        raise SystemExit(f"Unknown systems: {sorted(unknown)}")
    if args.api and set(systems) & set(ABLATION_SYSTEMS):
        raise SystemExit("The ablations need the in-process orchestrator: run them with --local.")

    from app.log import configure_logging

    settings = get_settings()
    settings.export_sdk_env()
    configure_logging("WARNING", stream=sys.stderr)
    cases = load_cases(args.split, args.ids)
    target = "local" if args.local else "api"
    run = Run(target, args.split, systems, settings, keep=args.keep)
    print(
        f"# {len(cases)} {args.split} cases · {', '.join(systems)} · {run.target}"
        f"{' ' + args.api if args.api else ''} · model {settings.gemini_model} · {git_sha()}",
        flush=True,
    )
    run.preflight = asyncio.run(preflight(settings))
    pings = ", ".join(secs_short(ms) for ms in run.preflight["pings_ms"])
    print(f"# pre-flight: one-word Gemini replies took {pings}", flush=True)
    if not run.preflight["ok"] and not args.force:
        print(
            f"# Gemini is degraded right now (median above {PREFLIGHT_MAX_MEDIAN_MS / 1000:g} s, "
            f"or more than {PREFLIGHT_MAX_SLOW} reply above {PREFLIGHT_SLOW_MS / 1000:g} s, for a "
            "one-word reply): the run would measure the outage. Try again later, or pass --force "
            "to run anyway (the pre-flight result is saved with the rows).",
            file=sys.stderr,
        )
        return 2
    t0 = time.perf_counter()
    if args.local:
        asyncio.run(run_local(run, cases, args.concurrency))
    else:
        token = os.environ.get("ADMIN_TOKEN") or settings.admin_reset_token
        if not token:
            raise SystemExit("Set ADMIN_TOKEN (Secret Manager admin-reset-token) for --api.")
        with tempfile.TemporaryDirectory(prefix="pauseguard-bench-") as tmp:
            api = ApiTarget(args.api, token, LocalTarget(settings, Path(tmp)))
            purged = asyncio.run(run_api(run, cases, args.concurrency, api))
        if purged:
            print(f"# purged benchmark traffic: {purged}")
    print(f"# done in {time.perf_counter() - t0:.0f} s")

    print(summary_table(run.rows))
    if "pauseguard" in run.rows:
        failed, asked = timeout_share(run.rows["pauseguard"])
        healthy = failed <= MAX_TIMEOUT_SHARE * asked
        print(
            f"# run health: {failed}/{asked} PauseGuard check-ins fell back to AMBER + review: "
            + ("OK" if healthy else f"DEGRADED (> {MAX_TIMEOUT_SHARE:.0%}): not reportable"),
            flush=True,
        )
    if not args.no_write:
        for path in run.write(args.api):
            print(f"# wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
