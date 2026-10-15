"""Benchmark report: eval/results/*_test_*.jsonl -> eval/reports/benchmark.md + 4 PNG charts.

    uv --directory backend run --group eval python ../eval/report.py
    ... --run 20261015T0130Z_local_test   # pick the primary run (default: the newest deployed
                                          # run, else the newest local run)
    ... --rating-form                     # also write eval/human_rating_form.md

Only test-split runs are reported (EVAL_PLAN §6). The main table, the breakdowns and the charts
come from the primary run. The ablations come from the newest local run that has them, and a
"local vs deployed" table appears when both targets have a run. Every number in the markdown is
computed here from the raw rows, so `make eval-report` rebuilds the same report from the same
results, and eval/human_ratings.csv is folded in when it exists.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import (  # noqa: E402
    ABLATION_SYSTEMS,
    MAIN_SYSTEMS,
    MAX_TIMEOUT_SHARE,
    SYSTEM_NAMES,
    VERDICTS,
    Row,
    Summary,
    age_band,
    confusion,
    group,
    load_pricing,
    model_price,
    pct,
    pct_ci,
    secs,
    summarise,
    timeout_share,
    usd,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
REPORT = ROOT / "eval" / "reports" / "benchmark.md"
CHARTS = ROOT / "eval" / "reports" / "charts"
RATING_FORM = ROOT / "eval" / "human_rating_form.md"
RATINGS = ROOT / "eval" / "human_ratings.csv"
RATING_ITEMS = 20
RUN_FILE = re.compile(  # <stamp>_<target>_<split>_<system>, as run_benchmark.py names them
    r"(?P<stamp>\d{8}T\d{4}Z)_(?P<target>local|api)_(?P<split>test|dev)_(?P<system>\w+)"
)
TYPOLOGIES = [
    "GOV_OFFICIAL_IMPERSONATION",
    "INVESTMENT",
    "JOB_TASK",
    "PHISHING",
    "ECOMMERCE",
    "FAKE_FRIEND",
    "ROMANCE",
    "BEC_INVOICE",
    "NONE",
]
PRD_ANSWER_P50_MS, PRD_ANSWER_P95_MS = 5000, 10000

# Chart colours: the dataviz skill's validated reference palette (light), checked with its
# validate_palette.js (blue/orange pass CVD and contrast); text in ink, never series colours.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
BLUE_RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]


# --- loading -------------------------------------------------------------------------------------


@dataclass
class RunData:
    run_id: str  # <stamp>_<target>_<split>
    target: str
    systems: dict[str, list[Row]]

    @property
    def meta(self) -> Row:
        rows = next(iter(self.systems.values()))
        return rows[0] if rows else {}


def load_runs(split: str = "test") -> dict[str, RunData]:
    runs: dict[str, RunData] = {}
    for path in sorted(RESULTS.glob(f"*_{split}_*.jsonl")):
        match = RUN_FILE.fullmatch(path.stem)
        if not match or match["split"] != split:
            continue  # e.g. evidence_dev_<stamp>.jsonl from phase 03
        stamp, target, system = match["stamp"], match["target"], match["system"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows = [r for r in rows if r["split"] == split]
        run_id = f"{stamp}_{target}_{split}"
        runs.setdefault(run_id, RunData(run_id, target, {})).systems[system] = rows
    return runs


def newest(runs: dict[str, RunData], target: str, need: tuple[str, ...]) -> RunData | None:
    found = [r for r in runs.values() if r.target == target and set(need) <= set(r.systems)]
    return max(found, key=lambda r: r.run_id) if found else None


# --- numbers -------------------------------------------------------------------------------------


def main_table(run: RunData, price: dict[str, float]) -> list[str]:
    lines = [
        "| System | Scam recall | Hard stop (RED) | FPR (legit stopped) | Legit → AMBER | "
        "Legit → RED | Precision | F1 | Typology acc. | p50 / p95 end to end | "
        "p50 / p95 answer → result | Cost / check |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for system in MAIN_SYSTEMS:
        if system not in run.systems:
            continue
        s = summarise(run.systems[system])
        bold = "**" if system == "pauseguard" else ""
        answer = f"{secs(s.answer_p50)} / {secs(s.answer_p95)}" if s.answer_n else "n/a"
        lines.append(
            f"| {bold}{SYSTEM_NAMES[system]}{bold} | {bold}{pct_ci(s.scams_stopped, s.scams)}"
            f"{bold} | {pct_ci(s.scams_red, s.scams)} | {bold}{pct_ci(s.legit_stopped, s.legit)}"
            f"{bold} | {pct(s.legit_amber_rate)} | {pct_ci(s.legit_red, s.legit)} | "
            f"{pct(s.precision)} | {_f(s.f1)} | {pct(s.typology_acc)} | "
            f"{secs(s.e2e_p50)} / {secs(s.e2e_p95)} | {answer} | {usd(s.cost_per_check(price))} |"
        )
    return lines


def deck_table(run: RunData, price: dict[str, float]) -> list[str]:
    """SUBMISSION_DECK slide 11, column for column."""
    lines = [
        "| System | Scam recall | FPR (legit→stopped) | Legit→RED | Typology acc. | "
        "p50 latency | Cost/check |",
        "|---|---|---|---|---|---|---|",
    ]
    for system in MAIN_SYSTEMS:
        if system not in run.systems:
            continue
        s = summarise(run.systems[system])
        latency = s.answer_p50 if system != "b0" else s.e2e_p50
        lines.append(
            f"| {SYSTEM_NAMES[system]} | {pct(s.recall)} | {pct(s.fpr)} | {pct(s.legit_red_rate)} "
            f"| {pct(s.typology_acc)} | {secs(latency)} | {usd(s.cost_per_check(price))} |"
        )
    return lines


def headline(run: RunData, price: dict[str, float]) -> str:
    b0 = summarise(run.systems["b0"]) if "b0" in run.systems else None
    b1 = summarise(run.systems["b1"]) if "b1" in run.systems else None
    pg = summarise(run.systems["pauseguard"])
    parts = [f"On {pg.n} held-out synthetic cases ({pg.scams} scams, {pg.legit} legitimate)"]
    if b0:
        parts.append(f"rules alone stopped {pct(b0.recall)} of scams")
    if b1:
        budget = run.meta.get("agent_timeout_s") or 0
        late = sum((r.get("answer_ms") or 0) > budget * 1000 for r in run.systems["b1"])
        parts.append(
            f"a single Gemini prompt with no time limit stopped {pct(b1.recall)} (and "
            f"{pct(b1.fpr)} of legitimate payments), but {late} of its {b1.n} answers took "
            f"longer than PauseGuard's {budget:g} s budget"
        )
    parts.append(
        f"PauseGuard stopped {pct(pg.recall)} with a {pct(pg.fpr)} false-positive rate "
        f"({pct(pg.legit_red_rate)} of legitimate payments held as RED), answering in "
        f"{secs(pg.answer_p50)} median after the customer's reply, at "
        f"{usd(pg.cost_per_check(price))} per check"
    )
    return parts[0] + ", " + "; ".join(parts[1:]) + "."


def breakdown(run: RunData, title: str, key: Any, order: list[str] | None = None) -> list[str]:
    systems = [s for s in MAIN_SYSTEMS if s in run.systems]
    groups = {s: group(run.systems[s], key) for s in systems}
    names = order or sorted({g for gs in groups.values() for g in gs})
    head = " | ".join(f"{SYSTEM_NAMES[s]} recall / FPR" for s in systems)
    lines = [f"| {title} | Scams / legit | {head} |", "|---" * (2 + len(systems)) + "|"]
    for name in names:
        cells = []
        rows = groups["pauseguard"].get(name, []) if "pauseguard" in groups else []
        sample = summarise(rows) if rows else None
        for s in systems:
            g = groups[s].get(name)
            if not g:
                cells.append("–")
                continue
            m = summarise(g)
            cells.append(f"{_frac(m.scams_stopped, m.scams)} / {_frac(m.legit_stopped, m.legit)}")
        n = f"{sample.scams} / {sample.legit}" if sample else "–"
        lines.append(f"| {name} | {n} | {' | '.join(cells)} |")
    return lines


def fallback_note(rows: list[Row]) -> list[str]:
    """Split "stopped" into stopped by the analysis vs. by the safe fallback (time budget)."""
    fb = [r for r in rows if r.get("needs_review")]
    if not fb:
        return []
    scams = [r["id"] for r in fb if r["label"] == "SCAM"]
    legit = [r["id"] for r in fb if r["label"] == "LEGIT"]
    analysed = [r for r in rows if not r.get("needs_review")]
    a = summarise(analysed)
    which = (
        f"{_n(len(scams), 'scam')} ({', '.join(scams) or 'none'}) and "
        f"{_n(len(legit), 'legitimate payment')} ({', '.join(legit) or 'none'})"
    )
    finished = f"recall {_frac(a.scams_stopped, a.scams)}, FPR {_frac(a.legit_stopped, a.legit)}"
    return [
        f"- The fallbacks: {which}, AMBER because the analysis did not finish in time, not "
        f"because it found anything. Counting only the checks whose analysis finished: "
        f"{finished}."
    ]


def ablation_health(run: RunData) -> list[str]:
    out = []
    for system in ABLATION_SYSTEMS:
        if system not in run.systems:
            continue
        failed, asked = timeout_share(run.systems[system])
        if failed > MAX_TIMEOUT_SHARE * asked:
            fb = [r for r in run.systems[system] if r.get("needs_review")]
            legit = sum(r["label"] == "LEGIT" for r in fb)
            name = SYSTEM_NAMES[system]
            out += [
                f"*{name}* ran into a slow endpoint: {failed} of {asked} checks hit the time "
                f"budget (AMBER + review), {legit} of them legitimate payments, so its FPR and "
                "typology accuracy are worse than its analysis. Read it as indicative.",
                "",
            ]
    return out


def latency_verdict(pg: Summary) -> str:
    met = (pg.answer_p50 or 0) <= PRD_ANSWER_P50_MS and (pg.answer_p95 or 0) <= PRD_ANSWER_P95_MS
    return (
        f"Answer → full customer result: p50 {secs(pg.answer_p50)}, p95 {secs(pg.answer_p95)} "
        f"against the PRD's {PRD_ANSWER_P50_MS / 1000:g} s / {PRD_ANSWER_P95_MS / 1000:g} s: "
        + (
            "**met**."
            if met
            else "**not met** on this run. The p95 sits at the 12 s budget, "
            "where a slow check falls back to AMBER + review."
        )
    )


def degraded_banner(run: RunData) -> list[str]:
    if "pauseguard" not in run.systems:
        return []
    failed, asked = timeout_share(run.systems["pauseguard"])
    if failed <= MAX_TIMEOUT_SHARE * asked:
        return []
    return [
        f"> **Degraded run: {failed} of {asked} PauseGuard check-ins hit the time budget** (more "
        f"than {MAX_TIMEOUT_SHARE:.0%}). The Gemini endpoint was slow; these numbers measure "
        "that, not the system, and are not reportable. See *Runs*.",
        "",
    ]


def b1_with_budget(run: RunData, budget_s: float | None) -> list[str]:
    """B1 held to the product's latency budget: an answer later than it is AMBER + review."""
    if "b1" not in run.systems or not budget_s:
        return []
    late = [r for r in run.systems["b1"] if (r.get("answer_ms") or 0) > budget_s * 1000]
    capped = [
        r | {"verdict": "AMBER", "needs_review": True} if r in late else r
        for r in run.systems["b1"]
    ]
    s = summarise(capped)
    return [
        f"- Held to PauseGuard's {budget_s:g} s budget (a later answer becomes AMBER + review, "
        f"as in the product), B1 would answer {len(late)} of {s.n} cases late and score recall "
        f"{pct(s.recall)}, FPR {pct(s.fpr)}, legit → RED {pct(s.legit_red_rate)}."
    ]


def per_typology(run: RunData) -> list[str]:
    systems = [s for s in MAIN_SYSTEMS if s in run.systems]
    lines = [
        "| Scam type | n | "
        + " | ".join(f"{SYSTEM_NAMES[s]} stopped" for s in systems)
        + " | PauseGuard named it |",
        "|---" * (3 + len(systems)) + "|",
    ]
    by = {s: group([r for r in run.systems[s] if r["label"] == "SCAM"], _typ) for s in systems}
    for t in TYPOLOGIES[:-1]:
        pg = by["pauseguard"].get(t, [])
        if not pg:
            continue
        cells = [_frac(summarise(by[s][t]).scams_stopped, len(by[s][t])) for s in systems]
        named = sum(r.get("typology_pred") == t for r in pg)
        lines.append(f"| {t} | {len(pg)} | {' | '.join(cells)} | {_frac(named, len(pg))} |")
    return lines


def ablation_table(run: RunData) -> list[str]:
    lines = [
        "| System | Scam recall | Hard stop (RED) | FPR | Legit → RED | Typology acc. | "
        "Scams never asked (fast path) | Needs review (failures) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for system in ("pauseguard", *ABLATION_SYSTEMS):
        if system not in run.systems:
            continue
        s = summarise(run.systems[system])
        lines.append(
            f"| {SYSTEM_NAMES[system]} | {pct_ci(s.scams_stopped, s.scams)} | "
            f"{pct(s.hard_stop_recall)} | {pct_ci(s.legit_stopped, s.legit)} | "
            f"{pct(s.legit_red_rate)} | {pct(s.typology_acc)} | {s.fast_path_scams} | "
            f"{s.failures} |"
        )
    return lines


def latency_table(rows: list[Row]) -> list[str]:
    asked = [r for r in rows if not r.get("fast_path")]
    agents = ["txn", "evidence", "intel", "verdict", "explainer", "total", "casefile"]
    labels = {
        "txn": "Transaction risk (at POST /checks)",
        "evidence": "Evidence agent (Gemini, multimodal)",
        "intel": "Watchlist lookups (+ web search, after the verdict)",
        "verdict": "Answer → verdict known",
        "explainer": "Explainer (Gemini, AMBER/RED only)",
        "total": "**Answer → full customer result**",
        "casefile": "Case file (Gemini, after the verdict, analyst only)",
    }
    lines = ["| Step | n | p50 | p95 |", "|---|---|---|---|"]
    for a in agents:
        vals = [r["latency_ms"].get(a) for r in asked if r.get("latency_ms", {}).get(a)]
        if vals:
            lines.append(
                f"| {labels[a]} | {len(vals)} | {secs(_p(vals, 0.5))} | {secs(_p(vals, 0.95))} |"
            )
    return lines


def cost_section(run: RunData, pricing: dict[str, Any], model: str) -> list[str]:
    price = model_price(pricing, model)
    later = price.get("list_price_from_2027") or price
    g = pricing["grounding"]
    lines = [
        f"Prices: `{model}`, Vertex AI Standard tier, global endpoint: "
        f"US${price['input_per_mtok']} per 1M input tokens and "
        f"US${price['output_per_mtok']} per 1M output tokens (thinking included), "
        f"introductory until {price.get('valid_until', '?')}; list price from 2027 "
        f"US${later['input_per_mtok']} / US${later['output_per_mtok']}. Source: "
        f"{pricing['source_url']} (retrieved {pricing['retrieved']}). Cost per check is the mean "
        "over **all** cases, so GREEN fast-path checks (no model call) count as $0.",
        "",
        "| System | Tokens in / out per check | Cost per check | Per 1,000 checks | "
        "At the 2027 list price |",
        "|---|---|---|---|---|",
    ]
    for system in MAIN_SYSTEMS:
        if system not in run.systems:
            continue
        s = summarise(run.systems[system])
        now, then = s.cost_per_check(price), s.cost_per_check(later)
        lines.append(
            f"| {SYSTEM_NAMES[system]} | {s.tokens_in:,.0f} / {s.tokens_out:,.0f} | {usd(now)} | "
            f"${now * 1000:,.2f} | {usd(then)} |"
        )
    pg = run.systems["pauseguard"]
    by_agent: Counter[str] = Counter()
    for r in pg:
        for agent, t in (r.get("tokens_by_agent") or {}).items():
            by_agent[f"{agent} in"] += t["in"]
            by_agent[f"{agent} out"] += t["out"]
    if by_agent:
        n = len(pg)
        parts = [
            f"{a} {by_agent[a + ' in'] / n:,.0f} / {by_agent[a + ' out'] / n:,.0f}"
            for a in ("evidence", "explainer", "casefile", "intel")
            if by_agent[a + " in"]
        ]
        lines += ["", "PauseGuard tokens in / out per check, by agent: " + "; ".join(parts) + "."]
    queries = [r.get("grounding_queries") or 0 for r in pg]
    if any(queries):
        mean = statistics.mean(queries)
        extra = usd(mean * g["per_1000_queries"] / 1000)
        lines += [
            "",
            f"Google Search grounding (the Scam-Intel agent, AMBER/RED only, after the verdict): "
            f"{sum(queries)} queries over {len(pg)} checks, {mean:.2f} per check. The first "
            f"{g['free_queries_per_month']:,} queries a month are free; past that, "
            f"US${g['per_1000_queries']:.0f} per 1,000 queries adds {extra} per check. Not "
            "included in the cost per check above.",
        ]
    return lines


def misses(run: RunData) -> list[str]:
    pg = run.systems["pauseguard"]
    missed = [r for r in pg if r["label"] == "SCAM" and r["verdict"] == "GREEN"]
    false_alarms = [r for r in pg if r["label"] == "LEGIT" and r["verdict"] != "GREEN"]
    lines = [
        f"**Scams PauseGuard let through ({len(missed)}).**",
        "",
        "| Case | Scam type | Lang | Evidence | Amount | Txn score | Why |",
        "|---|---|---|---|---|---|---|",
    ]
    if not missed:
        lines[-2:] = ["None."]
    for r in missed:
        why = "fast path: never asked" if r.get("fast_path") else _why(r)
        lines.append(
            f"| {r['id']} | {r['typology']} | {r['language']} | {r['evidence_type']} | "
            f"S${r['amount']:,.0f} | {r['txn_score']} | {why} |"
        )
    lines += [
        "",
        f"**Legitimate payments PauseGuard stopped ({len(false_alarms)}).**",
        "",
        "| Case | Kind | Lang | Evidence | Verdict | Read as | Why |",
        "|---|---|---|---|---|---|---|",
    ]
    if not false_alarms:
        lines[-2:] = ["None."]
    for r in false_alarms:
        lines.append(
            f"| {r['id']} | {r['scenario']} | {r['language']} | {r['evidence_type']} | "
            f"{r['verdict']}{' (needs review)' if r.get('needs_review') else ''} | "
            f"{r.get('typology_pred') or '–'} ({_f(r.get('confidence'))}) | {_why(r)} |"
        )
    return lines


def compare_targets(local: RunData, api: RunData) -> list[str]:
    lines = [
        "| Run | Where the agents ran | Recall | FPR | Legit → RED | Typology | "
        "p50 / p95 answer → result | Needs review |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run, where in (
        (local, "this laptop → Vertex AI global"),
        (api, "Cloud Run asia-southeast1"),
    ):
        s = summarise(run.systems["pauseguard"])
        lines.append(
            f"| `{run.run_id}` | {where} | {pct(s.recall)} | {pct(s.fpr)} | "
            f"{pct(s.legit_red_rate)} | {pct(s.typology_acc)} | {secs(s.answer_p50)} / "
            f"{secs(s.answer_p95)} | {s.failures} |"
        )
    return lines


def runs_table(runs: dict[str, RunData], primary: RunData) -> list[str]:
    """Every run on this split, reported or not, with its health (EVAL_PLAN §6: nothing hidden)."""
    lines = [
        "| Run | Target | Git | Pre-flight pings | PauseGuard timeouts (AMBER + review) | Status |",
        "|---|---|---|---|---|---|",
    ]
    for run in sorted(runs.values(), key=lambda r: r.run_id):
        meta = run.meta
        pings = ", ".join(
            f"{ms / 1000:.1f}" for ms in (meta.get("preflight") or {}).get("pings_ms", [])
        )
        if "pauseguard" in run.systems:
            failed, asked = timeout_share(run.systems["pauseguard"])
            health = f"{failed}/{asked}"
            healthy = failed <= MAX_TIMEOUT_SHARE * asked
        else:
            health, healthy = "–", True
        if run.run_id == primary.run_id:
            status = "**reported**" if healthy else "**reported, degraded**"
        elif not healthy:
            status = f"discarded: more than {MAX_TIMEOUT_SHARE:.0%} timeouts (endpoint degraded)"
        else:
            status = "kept, not the primary run"
        lines.append(
            f"| `{run.run_id}` | {run.target} | `{meta.get('git_sha')}` | {pings or '–'} s | "
            f"{health} | {status} |"
        )
    return lines


def ratings_section() -> list[str]:
    if not RATINGS.exists():
        return [
            "Not collected yet. `eval/human_rating_form.md` has 20 AMBER/RED explanations from "
            "this run for 3–5 raters (at least one aged 60+) to score 1–5; save the answers as "
            "`eval/human_ratings.csv` (`rater,rater_age_band,item,clarity,comment`) and run "
            "`make eval-report`."
        ]
    rows = list(csv.DictReader(RATINGS.open(encoding="utf-8")))
    scores = [int(r["clarity"]) for r in rows if r.get("clarity", "").strip()]
    if not scores:
        return ["`eval/human_ratings.csv` has no scores yet."]
    raters = {r["rater"] for r in rows}
    lines = [
        f"**Mean clarity {statistics.mean(scores):.1f} / 5** from {len(raters)} raters, "
        f"{len(scores)} ratings (`eval/human_ratings.csv`).",
        "",
        "| Rater age band | Raters | Mean clarity |",
        "|---|---|---|",
    ]
    for band, g in group(rows, lambda r: r.get("rater_age_band") or "unknown").items():
        s = [int(r["clarity"]) for r in g if r.get("clarity", "").strip()]
        lines.append(f"| {band} | {len({r['rater'] for r in g})} | {statistics.mean(s):.1f} |")
    return lines


# --- charts --------------------------------------------------------------------------------------


def charts(run: RunData, out_dir: Path = CHARTS) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "text.color": INK,
            "axes.labelcolor": INK_2,
            "axes.edgecolor": GRID,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    systems = [s for s in MAIN_SYSTEMS if s in run.systems]
    sums = {s: summarise(run.systems[s]) for s in systems}
    names = {"b0": "Rules only", "b1": "Gemini\nsingle prompt", "pauseguard": "PauseGuard"}
    paths = []

    # 1. Recall and FPR per system.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(systems))
    width = 0.36
    recall = [100 * (sums[s].recall or 0) for s in systems]
    fpr = [100 * (sums[s].fpr or 0) for s in systems]
    bars_r = ax.bar(
        [i - width / 2 - 0.01 for i in x], recall, width, color=BLUE, label="Scam recall"
    )
    bars_f = ax.bar(
        [i + width / 2 + 0.01 for i in x], fpr, width, color=ORANGE, label="False-positive rate"
    )
    for bars in (bars_r, bars_f):
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}%", (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", xytext=(0, 3), textcoords="offset points",
                        color=INK, fontsize=11)  # fmt: skip
    ax.set_xticks(list(x), [names[s] for s in systems])
    ax.set_ylim(0, 128)  # headroom: the legend sits above the 100% labels
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("% of cases")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", ncols=2)
    ax.set_title(f"Scams stopped vs legitimate payments stopped ({sums[systems[0]].n} test cases)")
    paths.append(_save(fig, out_dir, "benchmark_recall_fpr.png"))

    # 2. Confusion matrix (label x verdict) per system.
    fig, axes = plt.subplots(1, len(systems), figsize=(3.6 * len(systems), 3.4))
    for ax, s in zip(axes if len(systems) > 1 else [axes], systems, strict=True):
        m = confusion(run.systems[s])
        grid = [[m[label][v] for v in VERDICTS] for label in ("SCAM", "LEGIT")]
        _heat(ax, grid, VERDICTS, ["Scam", "Legit"], max(max(r) for r in grid))
        ax.set_title(names[s].replace("\n", " "))
        ax.set_xlabel("Verdict")
    fig.suptitle("Verdict by true label", fontweight="bold")
    paths.append(_save(fig, out_dir, "benchmark_confusion.png"))

    # 3. PauseGuard latency, answer -> full result.
    pg = sums["pauseguard"]
    vals = [r["answer_ms"] / 1000 for r in run.systems["pauseguard"] if r.get("answer_ms")]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(vals, bins=[i * 0.5 for i in range(int(max(vals) / 0.5) + 2)], color=BLUE,
            edgecolor=SURFACE, linewidth=2)  # fmt: skip
    for ms, label in ((pg.answer_p50, "p50"), (pg.answer_p95, "p95")):
        if ms:
            ax.axvline(ms / 1000, color=INK_2, linestyle="--", linewidth=1.5)
            top = ax.get_ylim()[1] * 0.95
            ax.annotate(f"{label} {ms / 1000:.1f} s", (ms / 1000, top), xytext=(4, 0),
                        textcoords="offset points", color=INK, fontsize=10)  # fmt: skip
    ax.set_xlabel("Seconds from the customer's answer to the full result on screen")
    ax.set_ylabel("Checks")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(f"PauseGuard latency ({len(vals)} checks with a check-in)")
    paths.append(_save(fig, out_dir, "benchmark_latency.png"))

    # 4. Typology confusion (PauseGuard): expected vs named.
    rows = run.systems["pauseguard"]
    cols = [*TYPOLOGIES, "UNKNOWN", "not asked"]
    present = [t for t in TYPOLOGIES if any(r["typology"] == t for r in rows)]
    grid = [
        [sum(r["typology"] == t and _pred(r) == c for r in rows) for c in cols] for t in present
    ]
    keep = [i for i, c in enumerate(cols) if any(row[i] for row in grid) or c in present]
    fig, ax = plt.subplots(figsize=(10, 6))
    short = {"GOV_OFFICIAL_IMPERSONATION": "GOV_IMPERSONATION"}
    _heat(ax, [[row[i] for i in keep] for row in grid], [short.get(cols[i], cols[i]) for i in keep],
          [short.get(t, t) for t in present], max(max(r) for r in grid))  # fmt: skip
    ax.tick_params(axis="x", rotation=40)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
    ax.set_xlabel("PauseGuard's typology")
    ax.set_ylabel("True typology")
    ax.set_title("Scam type: true vs named by PauseGuard")
    paths.append(_save(fig, out_dir, "benchmark_typology.png"))
    return paths


def _heat(ax: Any, grid: list[list[int]], cols: list[str], rows: list[str], top: int) -> None:
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=max(top, 1), aspect="auto")
    ax.set_xticks(range(len(cols)), cols)
    ax.set_yticks(range(len(rows)), rows)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            if v == 0 and len(cols) > 3:  # a big matrix: leave empty cells blank
                continue
            dark = v > 0.55 * top
            ax.text(j, i, str(v), ha="center", va="center", fontsize=11,
                    color=SURFACE if dark else INK)  # fmt: skip
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)


def _save(fig: Any, out_dir: Path, name: str) -> Path:
    path = out_dir / name
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    import matplotlib.pyplot as plt

    plt.close(fig)
    return path


# --- rating form ---------------------------------------------------------------------------------


def rating_form(run: RunData) -> Path:
    stopped = [r for r in run.systems["pauseguard"] if r["verdict"] != "GREEN" and r.get("message")]
    rng = random.Random(f"rating:{run.run_id}")
    items = sorted(rng.sample(stopped, min(RATING_ITEMS, len(stopped))), key=lambda r: r["id"])
    lines = [
        "# PauseGuard explanation clarity rating",
        "",
        f"{len(items)} explanations PauseGuard showed when it paused (AMBER) or held (RED) a "
        f"payment in benchmark run `{run.run_id}`, picked at random. Everything is synthetic.",
        "",
        "**For each one, imagine you were about to send this payment and the bank showed you "
        "this message.** Rate 1–5: *How clearly does it tell you why the payment was stopped "
        "and what to do next?* (1 = I don't understand it, 5 = completely clear). A comment is "
        "optional. Please ask 3–5 people, including at least one aged 60 or over.",
        "",
        "Save the answers as `eval/human_ratings.csv` with the columns "
        "`rater,rater_age_band,item,clarity,comment` (age band: under 40, 40-59, 60+), one row "
        "per rater and item, then run `make eval-report`.",
        "",
    ]
    for i, r in enumerate(items, 1):
        m = r["message"]
        lines += [
            f"## {i}. {r['verdict']} · S${r['amount']:,.0f} · {m['language']}",
            "",
            f"**{m['headline']}**",
            "",
            m["body"],
            "",
        ]
        lines += [f"- {f['text']}" for f in m.get("flag_explanations", [])]
        lines += ["", "Clarity (1–5): ___   Comment: ___", ""]
    RATING_FORM.write_text("\n".join(lines), encoding="utf-8")
    return RATING_FORM


# --- report --------------------------------------------------------------------------------------


def build(runs: dict[str, RunData], primary: RunData, split: str = "test") -> str:
    pricing = load_pricing()
    meta = primary.meta
    model = meta["model"]
    price = model_price(pricing, model)
    pg_rows = primary.systems["pauseguard"]
    pg = summarise(pg_rows)
    # The trigger changed on 15 Oct (DECISIONS): a new payee always gets the check-in.
    fast_rule = {True: ", known payees only", False: ", new payees too"}.get(
        meta.get("checkin_every_new_payee"), ""
    )
    local = newest(runs, "local", ("pauseguard",))
    api = newest(runs, "api", ("pauseguard",))
    ablations = newest(runs, "local", ("pauseguard", *ABLATION_SYSTEMS))
    where = (
        f"the deployed API ({meta.get('api')}, Cloud Run asia-southeast1)"
        if primary.target == "api"
        else "the in-process orchestrator on a laptop (Singapore → Vertex AI global endpoint)"
    )
    pinned = (
        f" Transaction history: synthetic seed {meta.get('seed_end_date')}, scored as of "
        f"{meta.get('as_of')}."
        if meta.get("as_of")
        else " Transaction scores: the deployed BigQuery data, scored at request time."
    )
    out = [
        "# Benchmark: rules vs a single Gemini prompt vs PauseGuard",
        "",
        "<!-- Generated by eval/report.py from eval/results/; edit the code, not this file. -->",
        "",
        f"**Run `{primary.run_id}`** · model `{model}` (thinking {meta.get('thinking')}, media "
        f"{meta.get('media_resolution')}) · git `{meta.get('git_sha')}` · {where}.{pinned} "
        f"Customer-facing budget {meta.get('agent_timeout_s'):g} s. Report generated "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC.",
        "",
        (
            f"Test split only: {pg.n} cases ({pg.scams} scams, {pg.legit} legitimate hard "
            "negatives), frozen before any of these systems ran on it (`eval/TEST_SPLIT_HASH`, "
            "`make eval-verify`). Nothing was tuned on it."
            if split == "test"
            else f"> **DEV SPLIT PREVIEW, not for reporting** (EVAL_PLAN §6): {pg.n} cases."
        ),
        "",
        *degraded_banner(primary),
        "## Headline",
        "",
        f"> {headline(primary, price)}",
        "",
        "## Results",
        "",
        "SCAM is the positive class; *stopped* means AMBER or RED. Rates show the Wilson 95% "
        f"interval in brackets: with {pg.scams} + {pg.legit} cases, a few points either way is "
        "noise.",
        "",
        *main_table(primary, price),
        "",
        "- **End to end** = transaction risk + (for systems that read the conversation) the "
        "model work after the customer's answer. **Answer → result** = from the customer's "
        "answer to the full message on screen (PauseGuard: checks with a check-in; the PRD "
        f"target is p50 ≤ {PRD_ANSWER_P50_MS / 1000:g} s, p95 ≤ {PRD_ANSWER_P95_MS / 1000:g} s).",
        f"- PauseGuard asked {pg.n - pg.fast_path_scams - pg.fast_path_legit} of {pg.n} "
        f"customers the check-in question; {pg.fast_path_scams + pg.fast_path_legit} transfers "
        f"took the GREEN fast path (a low score with no check-in{fast_rule}; "
        f"{pg.fast_path_scams} of them scams). {pg.failures} checks fell back to AMBER + human "
        "review (a model error or the time budget), which counts as stopped.",
        *fallback_note(pg_rows),
        "- B1 gets the same inputs (built by the evidence agent's own code), the transaction "
        "score and reasons, no time budget and one retry; see `eval/baselines/single_prompt.py`.",
        *b1_with_budget(primary, meta.get("agent_timeout_s")),
        "",
        "For the deck (SUBMISSION_DECK slide 11):",
        "",
        *deck_table(primary, price),
        "",
        "![Recall and false-positive rate](charts/benchmark_recall_fpr.png)",
        "",
        "![Verdict by true label](charts/benchmark_confusion.png)",
        "",
    ]
    if ablations:
        out += [
            "## Ablations: where the misses come from",
            "",
            f"Local run `{ablations.run_id}`. *Always ask* turns the GREEN fast path off, so every "
            "transfer gets the check-in; *answer only* drops the screenshot, PDF or pasted chat "
            "and keeps the customer's typed answer. In both, the case file and the web search "
            "(which run after the verdict and never change it) are skipped.",
            "",
            *ablation_table(ablations),
            "",
            *ablation_health(ablations),
        ]
    out += [
        "## Fairness breakdowns",
        "",
        "Recall (scams stopped / scams) and FPR (legit stopped / legit) per group. Small groups: "
        "read them as a check for large gaps, not as precise rates.",
        "",
        *breakdown(primary, "Language", lambda r: r["language"], ["en", "zh"]),
        "",
        *breakdown(
            primary, "Evidence", lambda r: r["evidence_type"], ["image", "pdf", "text", "none"]
        ),
        "",
        *breakdown(
            primary, "Customer age", lambda r: age_band(r.get("age")), ["under 40", "40-59", "60+"]
        ),
        "",
        *breakdown(primary, "Difficulty", lambda r: r["difficulty"], ["obvious", "subtle"]),
        "",
        "## By scam type",
        "",
        *per_typology(primary),
        "",
        f"Typology accuracy on the scams PauseGuard analysed (excluding the fast path): "
        f"{pct(pg.typology_acc_analysed)} ({pg.typology_correct_analysed}/{pg.scams_analysed}).",
        "",
        "![Typology confusion](charts/benchmark_typology.png)",
        "",
        "## Latency",
        "",
        latency_verdict(pg),
        "",
        "PauseGuard, per step (checks with a check-in):",
        "",
        *latency_table(pg_rows),
        "",
        "![PauseGuard latency](charts/benchmark_latency.png)",
        "",
        "## Cost",
        "",
        *cost_section(primary, pricing, model),
        "",
    ]
    if local and api:
        out += [
            "## Local vs deployed",
            "",
            "The same test split through the in-process orchestrator and through the deployed "
            "API. The deployed run scores transactions on the BigQuery copy at request time, so a "
            "few scores (and so B0) can differ from the pinned local run.",
            "",
            *compare_targets(local, api),
            "",
        ]
    out += [
        "## Misses and false alarms (PauseGuard)",
        "",
        *misses(primary),
        "",
        "## Explanation clarity (human rating)",
        "",
        *ratings_section(),
        "",
        "## Runs",
        "",
        "Every benchmark run on this split. A run is reportable when the Gemini endpoint passed "
        "the pre-flight check (5 one-word replies: median ≤ 3 s, at most one above 10 s) and at "
        f"most {MAX_TIMEOUT_SHARE:.0%} of PauseGuard's check-ins fell back to AMBER + review; a "
        "run above that measured a degraded endpoint and is discarded, not hidden.",
        "",
        *runs_table(runs, primary),
        "",
        "## Limitations",
        "",
        "- **Synthetic data and our own labels.** The cases were drafted from public scam "
        "advisories, rewritten with fictional people, banks and numbers, and reviewed by us; "
        "real scam messages are messier and adapt. No real bank traffic was used.",
        "- **Small sample.** 50 scams and 50 legitimate payments; the brackets show how wide the "
        "uncertainty is. Subgroups (age, evidence type) are smaller still.",
        "- **The mix is not the real base rate.** Half the cases are scams, while almost all real "
        "payments are legitimate, so precision here is far higher than it would be in "
        "production. The false-positive rate is the number to watch.",
        "- **No watchlist hits.** Eval entities are kept off the seed watchlist on purpose, so "
        "the watchlist's hard stops (which would help both B0 and PauseGuard) are not measured.",
        "- **Latency depends on where it runs** (see the run line at the top); Gemini latency on "
        "the global endpoint varies by time of day.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "make eval-verify                    # the test split is unchanged",
        "make eval                           # local run (all systems) + this report",
        "make eval API=deployed              # PauseGuard, B0, B1 through the live Cloud Run API",
        "make eval-report                    # rebuild this report from eval/results/",
        "```",
        "",
        "Raw rows (one per case and system, with the model, git SHA and timings): "
        + ", ".join(
            f"`eval/results/{primary.run_id.rsplit('_', 1)[0]}_test_{s}.jsonl`"
            for s in primary.systems
        )
        + ".",
        "",
    ]
    return "\n".join(out)


def _why(r: Row) -> str:
    reasons = r.get("reasons") or []
    flags = r.get("top_flags") or []
    text = "; ".join(reasons[:2]) or "no reasons recorded"
    if flags:
        text += f" · flags {', '.join(flags[:3])}"
    return text.replace("|", "/")


def _typ(r: Row) -> str:
    return str(r["typology"])


def _pred(r: Row) -> str:
    if r.get("fast_path"):
        return "not asked"
    return str(r.get("typology_pred") or "UNKNOWN")


def _n(k: int, noun: str) -> str:
    return f"{k} {noun}" + ("" if k == 1 else "s")


def _frac(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "–"


def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _p(vals: list[int], q: float) -> int | None:
    from metrics import pctl

    return pctl(vals, q)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--run", help="primary run id, e.g. 20261015T0130Z_local_test")
    p.add_argument("--rating-form", action="store_true", help="write eval/human_rating_form.md")
    p.add_argument("--split", default="test", choices=["test", "dev"], help="dev: a preview")
    p.add_argument("--out", type=Path, help="write the report here (required for --split dev)")
    args = p.parse_args(argv)
    if args.split != "test" and not args.out:
        raise SystemExit("A dev-split report is a preview: pass --out (never eval/reports/).")
    out: Path = args.out or REPORT

    runs = load_runs(args.split)
    if args.run:
        if args.run not in runs:
            raise SystemExit(f"No {args.split} run {args.run!r} in eval/results/ ({sorted(runs)})")
        primary = runs[args.run]
    else:
        found = newest(runs, "api", MAIN_SYSTEMS) or newest(runs, "local", MAIN_SYSTEMS)
        if found is None:
            raise SystemExit(f"No complete {args.split} run in eval/results/: run `make eval`.")
        primary = found
    out.write_text(build(runs, primary, args.split), encoding="utf-8")
    print(f"# wrote {out} from {primary.run_id}")
    for path in charts(primary, out.parent / "charts"):
        print(f"# wrote {path}")
    if args.rating_form:
        print(f"# wrote {rating_form(primary).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
