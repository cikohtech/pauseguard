"""Benchmark metrics (EVAL_PLAN §4), pure functions over result rows (eval/results/*.jsonl).

SCAM is the positive class and "stopped" means the verdict is AMBER or RED.
  recall            scams stopped / scams
  hard-stop recall  scams RED / scams
  FPR               legit stopped / legit, split into legit AMBER and legit RED (the costly one)
  precision, F1     on "stopped"
  typology accuracy exact match on the scams (a scam that was never analysed counts as wrong)
  latency           nearest-rank p50/p95: end to end per case, and answer -> result
  cost              tokens x the published price (eval/pricing.yaml), mean over all cases
Rates come with Wilson 95% intervals, because 50 scams and 50 legit payments are a small sample.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Row = dict[str, Any]
STOP = {"AMBER", "RED"}
NOT_SCAM = {"NONE", "UNKNOWN", None}
VERDICTS = ("GREEN", "AMBER", "RED")
MAIN_SYSTEMS = ("b0", "b1", "pauseguard")  # the report's main table
ABLATION_SYSTEMS = ("pg_always", "pg_noevidence")  # --local only
# A reportable run: at most 5% of PauseGuard's check-ins fell back to AMBER + review (a model
# error or the time budget). Above that the run measured a degraded Gemini endpoint, not the
# system; it is discarded but stays in git and in the report's run table (DECISIONS 2026-10-15).
MAX_TIMEOUT_SHARE = 0.05
PRICING = Path(__file__).with_name("pricing.yaml")
SYSTEM_NAMES = {
    "b0": "Rules only (B0)",
    "b1": "Gemini single prompt (B1)",
    "pauseguard": "PauseGuard",
    "pg_always": "PauseGuard, always ask (no fast path)",
    "pg_noevidence": "PauseGuard, answer only (no evidence)",
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes out of n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def pctl(values: Iterable[float | int | None], q: float) -> int | None:
    """Nearest-rank percentile (q in 0..1); None values are skipped."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    return round(xs[max(0, math.ceil(q * len(xs)) - 1)])


def ratio(k: int, n: int) -> float | None:
    return k / n if n else None


@dataclass
class Summary:
    n: int
    scams: int
    legit: int
    scams_stopped: int
    scams_red: int
    legit_amber: int
    legit_red: int
    typology_correct: int
    scams_analysed: int
    typology_correct_analysed: int
    fast_path_scams: int
    fast_path_legit: int
    failures: int  # needs_review: a model failure or timeout (the safe AMBER)
    e2e_p50: int | None
    e2e_p95: int | None
    answer_p50: int | None
    answer_p95: int | None
    answer_n: int
    tokens_in: float  # mean per case, all cases
    tokens_out: float
    grounding_queries: float  # mean per case (local runs only)
    has_typology: bool

    @property
    def legit_stopped(self) -> int:
        return self.legit_amber + self.legit_red

    @property
    def stopped(self) -> int:
        return self.scams_stopped + self.legit_stopped

    @property
    def recall(self) -> float | None:
        return ratio(self.scams_stopped, self.scams)

    @property
    def hard_stop_recall(self) -> float | None:
        return ratio(self.scams_red, self.scams)

    @property
    def fpr(self) -> float | None:
        return ratio(self.legit_stopped, self.legit)

    @property
    def legit_amber_rate(self) -> float | None:
        return ratio(self.legit_amber, self.legit)

    @property
    def legit_red_rate(self) -> float | None:
        return ratio(self.legit_red, self.legit)

    @property
    def precision(self) -> float | None:
        return ratio(self.scams_stopped, self.stopped)

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def typology_acc(self) -> float | None:
        return ratio(self.typology_correct, self.scams) if self.has_typology else None

    @property
    def typology_acc_analysed(self) -> float | None:
        if not self.has_typology:
            return None
        return ratio(self.typology_correct_analysed, self.scams_analysed)

    def cost_per_check(self, price: dict[str, float]) -> float:
        return (
            self.tokens_in * price["input_per_mtok"] + self.tokens_out * price["output_per_mtok"]
        ) / 1e6


def summarise(rows: list[Row]) -> Summary:
    scams = [r for r in rows if r["label"] == "SCAM"]
    legit = [r for r in rows if r["label"] == "LEGIT"]
    analysed = [r for r in scams if not r.get("fast_path")]
    n = len(rows) or 1
    answers = [r.get("answer_ms") for r in rows if r.get("answer_ms") is not None]
    return Summary(
        n=len(rows),
        scams=len(scams),
        legit=len(legit),
        scams_stopped=sum(r["verdict"] in STOP for r in scams),
        scams_red=sum(r["verdict"] == "RED" for r in scams),
        legit_amber=sum(r["verdict"] == "AMBER" for r in legit),
        legit_red=sum(r["verdict"] == "RED" for r in legit),
        typology_correct=sum(r.get("typology_pred") == r["typology"] for r in scams),
        scams_analysed=len(analysed),
        typology_correct_analysed=sum(r.get("typology_pred") == r["typology"] for r in analysed),
        fast_path_scams=sum(bool(r.get("fast_path")) for r in scams),
        fast_path_legit=sum(bool(r.get("fast_path")) for r in legit),
        failures=sum(bool(r.get("needs_review")) for r in rows),
        e2e_p50=pctl((r.get("e2e_ms") for r in rows), 0.5),
        e2e_p95=pctl((r.get("e2e_ms") for r in rows), 0.95),
        answer_p50=pctl(answers, 0.5),
        answer_p95=pctl(answers, 0.95),
        answer_n=len(answers),
        tokens_in=sum(r["tokens"]["in"] for r in rows) / n,
        tokens_out=sum(r["tokens"]["out"] for r in rows) / n,
        grounding_queries=sum(r.get("grounding_queries") or 0 for r in rows) / n,
        has_typology=any(r.get("typology_pred") is not None for r in rows),
    )


def timeout_share(rows: list[Row]) -> tuple[int, int]:
    """(checks that fell back to AMBER + review, checks that were analysed): the run's health."""
    asked = [r for r in rows if not r.get("fast_path")]
    return sum(bool(r.get("needs_review")) for r in asked), len(asked)


def confusion(rows: list[Row]) -> dict[str, dict[str, int]]:
    """label -> verdict -> count."""
    out = {label: dict.fromkeys(VERDICTS, 0) for label in ("SCAM", "LEGIT")}
    for r in rows:
        out[r["label"]][r["verdict"]] += 1
    return out


def age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    return "60+" if age >= 60 else ("40-59" if age >= 40 else "under 40")


def group(rows: list[Row], key: Callable[[Row], str]) -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {}
    for r in rows:
        out.setdefault(key(r), []).append(r)
    return dict(sorted(out.items()))


# --- formatting ------------------------------------------------------------------------------


def pct(x: float | None, digits: int = 0) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def pct_ci(k: int, n: int) -> str:
    """'92% (81–97)': the rate with its Wilson 95% interval."""
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} ({lo * 100:.0f}–{hi * 100:.0f})"


def secs(ms: int | None) -> str:
    if ms is None:
        return "n/a"
    return f"{ms} ms" if ms < 1000 else f"{ms / 1000:.1f} s"


def usd(x: float) -> str:
    return "$0" if x == 0 else (f"${x:.4f}" if x < 0.01 else f"${x:.3f}")


def summary_table(rows_by_system: dict[str, list[Row]]) -> str:
    """A compact console table (the runner prints it at the end)."""
    head = "| System | n | Recall | Hard stop | FPR | Legit→RED | Typology | p50 e2e | p50 answer |"
    lines = [head + " Failed |", "|---" * 10 + "|"]
    for system, rows in rows_by_system.items():
        s = summarise(rows)
        lines.append(
            f"| {SYSTEM_NAMES.get(system, system)} | {s.n} | {pct(s.recall)} | "
            f"{pct(s.hard_stop_recall)} | {pct(s.fpr)} | {pct(s.legit_red_rate)} | "
            f"{pct(s.typology_acc)} | {secs(s.e2e_p50)} | {secs(s.answer_p50)} | {s.failures} |"
        )
    return "\n".join(lines)


def load_pricing(path: Path = PRICING) -> dict[str, Any]:
    import yaml

    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def model_price(pricing: dict[str, Any], model: str) -> dict[str, float]:
    """The model's current price; KeyError if eval/pricing.yaml doesn't list it (never guess)."""
    try:
        price: dict[str, float] = pricing["models"][model]
    except KeyError:
        raise KeyError(f"{model} is not in eval/pricing.yaml: add its published price") from None
    return price
