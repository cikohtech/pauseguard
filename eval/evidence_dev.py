"""Evidence agent on the DEV split only (phase 03 prompt tuning). Never runs the test split.

    uv --directory backend run python ../eval/evidence_dev.py            # all 60 dev cases
    uv --directory backend run python ../eval/evidence_dev.py --ids ev_0051 ev_0060

Prints typology accuracy and every miss, writes the raw runs to eval/results/ (git-ignored) and
a summary to eval/reports/evidence_dev.md. "Evidence-only stop" previews the AMBER rules of
AGENTS_SPEC §4 that depend on the evidence alone (a scam typology with confidence >= 0.5, a HIGH
flag, or an injection); the real verdict also uses the transaction score and intel (phase 04).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.evidence_agent import (  # noqa: E402
    EvidenceItem,
    EvidenceRequest,
    EvidenceRun,
    analyse_evidence,
    load_prompt,
)
from app.config import get_settings  # noqa: E402
from app.log import configure_logging  # noqa: E402
from app.models.schemas import Transfer  # noqa: E402

CASES = ROOT / "data" / "eval" / "cases.jsonl"
RESULTS = ROOT / "eval" / "results"
REPORT = ROOT / "eval" / "reports" / "evidence_dev.md"
NOT_SCAM = {"NONE", "UNKNOWN"}


def load_dev(ids: list[str] | None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    dev = [r for r in rows if r["split"] == "dev"]
    if ids:
        test_ids = {r["id"] for r in rows if r["split"] != "dev"} & set(ids)
        if test_ids:
            raise SystemExit(f"Refusing to run test-split cases: {sorted(test_ids)}")
        dev = [r for r in dev if r["id"] in set(ids)]
    return dev


def to_request(case: dict[str, Any]) -> EvidenceRequest:
    t = {k: v for k, v in case["transfer"].items() if k not in {"customer_id", "is_new_payee"}}
    items = [
        EvidenceItem(text=e["text"]) if e["type"] == "text" else EvidenceItem(uri=e["path"])
        for e in case["evidence"]
    ]
    return EvidenceRequest(
        customer_text=case["customer_answer"],
        quick_reply=case["quick_reply"],
        items=items,
        transfer=Transfer(**t),
        check_id=f"dev_{case['id']}",
    )


def evidence_stop(run: EvidenceRun, amber_conf: float) -> bool:
    a = run.analysis
    scam_typology = a.typology_guess not in NOT_SCAM and a.typology_confidence >= amber_conf
    high = any(f.severity == "HIGH" for f in a.red_flags)
    return run.failed or scam_typology or high or a.injection_attempt_detected


async def run_all(cases: list[dict[str, Any]], concurrency: int) -> list[tuple[dict, EvidenceRun]]:
    sem = asyncio.Semaphore(concurrency)

    async def one(case: dict[str, Any]) -> tuple[dict, EvidenceRun]:
        async with sem:
            return case, await analyse_evidence(to_request(case))

    return await asyncio.gather(*(one(c) for c in cases))


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.0%})" if d else "n/a"


def summarise(results: list[tuple[dict, EvidenceRun]], amber_conf: float) -> str:
    n = len(results)
    scams = [(c, r) for c, r in results if c["label"] == "SCAM"]
    legit = [(c, r) for c, r in results if c["label"] == "LEGIT"]
    typ_ok = [(c, r) for c, r in results if r.analysis.typology_guess == c["typology"]]
    scam_named = [r for c, r in scams if r.analysis.typology_guess not in NOT_SCAM]
    legit_none = [r for c, r in legit if r.analysis.typology_guess == "NONE"]
    stop_scam = [r for c, r in scams if evidence_stop(r, amber_conf)]
    stop_legit = [(c, r) for c, r in legit if evidence_stop(r, amber_conf)]
    inj = [(c, r) for c, r in results if c["injection"]]
    inj_ok = [r for c, r in inj if r.analysis.injection_attempt_detected]
    inj_fp = [c for c, r in results if not c["injection"] and r.analysis.injection_attempt_detected]
    failed = [c for c, r in results if r.failed]
    lat = sorted(r.latency_ms for _, r in results)
    boxes = sum(1 for _, r in results for f in r.analysis.red_flags if f.box_2d)
    tok_in = statistics.mean(r.tokens.in_ for _, r in results)
    tok_out = statistics.mean(r.tokens.out for _, r in results)

    lines = [
        f"- Cases: {n} (dev split only; {len(scams)} scam, {len(legit)} legit)",
        f"- **Typology accuracy (exact): {pct(len(typ_ok), n)}**",
        f"- Scams given a scam typology: {pct(len(scam_named), len(scams))}",
        f"- Legit given NONE: {pct(len(legit_none), len(legit))}",
        f"- Evidence-only stop, scams: {pct(len(stop_scam), len(scams))}",
        f"- Evidence-only stop, legit (false alarms): {pct(len(stop_legit), len(legit))}",
        f"- Injection detected: {pct(len(inj_ok), len(inj))}; false injection hits: {len(inj_fp)}",
        f"- Model failures (fallback): {len(failed)}",
        f"- Flags with a box: {boxes}",
        f"- Latency p50 {lat[n // 2]} ms, p95 {lat[min(n - 1, int(n * 0.95))]} ms; "
        f"tokens in/out (mean) {tok_in:.0f}/{tok_out:.0f}",
    ]

    by_typ: dict[str, list[bool]] = {}
    for c, r in results:
        by_typ.setdefault(c["typology"], []).append(r.analysis.typology_guess == c["typology"])
    lines += ["", "| Expected typology | Correct |", "|---|---|"]
    lines += [f"| {t} | {pct(sum(v), len(v))} |" for t, v in sorted(by_typ.items())]

    misses = [(c, r) for c, r in results if r.analysis.typology_guess != c["typology"]]
    misses += [(c, r) for c, r in stop_legit if (c, r) not in misses]
    if misses:
        lines += ["", "| Case | Label | Lang | Evidence | Expected | Got (conf) | Flags |"]
        lines += ["|---|---|---|---|---|---|---|"]
        for c, r in sorted(misses, key=lambda x: x[0]["id"]):
            a = r.analysis
            flags = ", ".join(f"{f.code}:{f.severity[0]}" for f in a.red_flags) or "-"
            ev = "+".join(e["type"] for e in c["evidence"]) or "none"
            lines.append(
                f"| {c['id']} | {c['label']} | {c['language']} | {ev} | {c['typology']} | "
                f"{a.typology_guess} ({a.typology_confidence:.2f}) | {flags} |"
            )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--ids", nargs="*", help="only these dev cases")
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--no-report", action="store_true", help="don't rewrite the markdown report")
    args = p.parse_args()

    settings = get_settings()
    configure_logging("WARNING", stream=sys.stderr)
    cases = load_dev(args.ids)
    started = time.perf_counter()
    results = asyncio.run(run_all(cases, args.concurrency))
    wall = time.perf_counter() - started

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw = RESULTS / f"evidence_dev_{stamp}.jsonl"
    with raw.open("w", encoding="utf-8") as fh:
        for c, r in results:
            row = {
                "id": c["id"],
                "label": c["label"],
                "typology": c["typology"],
                "failed": r.failed,
                "attempts": r.attempts,
                "latency_ms": r.latency_ms,
                "tokens": {"in": r.tokens.in_, "out": r.tokens.out},
                "analysis": r.analysis.model_dump(mode="json"),
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    version = next(
        (ln.split(":")[0].strip("- ").strip() for ln in _changelog() if ln.startswith("- v")), "?"
    )
    body = summarise(results, settings.fusion_amber_confidence)
    header = (
        f"Model `{settings.gemini_model}` (thinking {settings.gemini_thinking_level}, "
        f"media {settings.gemini_media_resolution}), "
        f"prompt {version}, {stamp}, wall {wall:.0f} s. "
        f"Raw runs: `eval/results/{raw.name}` (git-ignored)."
    )
    print(header + "\n\n" + body)
    if not args.ids and not args.no_report:
        REPORT.write_text(
            "# Evidence agent: dev split\n\n"
            "Phase 03 tuning run of the evidence agent alone, on the **dev split only** (the test "
            "split is never used for tuning; EVAL_PLAN §3). Produced by `eval/evidence_dev.py`.\n\n"
            + header
            + "\n\n"
            + body
            + "\n",
            encoding="utf-8",
        )
    load_prompt.cache_clear()
    errors = Counter(r.error for _, r in results if r.failed)
    if errors:
        print("\nFailures:", dict(errors), file=sys.stderr)
    return 0


def _changelog() -> list[str]:
    text = (ROOT / "backend/app/agents/prompts/evidence.md").read_text(encoding="utf-8")
    comment = text.split("-->")[0]
    return [ln.strip() for ln in comment.splitlines()][::-1]  # newest entry last in the file


if __name__ == "__main__":
    raise SystemExit(main())
