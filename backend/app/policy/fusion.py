"""Fusion policy (AGENTS_SPEC §4): plain rules turn the agents' findings into GREEN/AMBER/RED.

Not an LLM, so the verdict is auditable and an injected instruction can never approve a payment.
Thresholds come from config (`FUSION_*`) and are frozen before the test split runs (EVAL_PLAN).

RED, at any amount (hard-stop signals):
  - a watchlist match (payee account, or a phone, URL or account in the evidence)
  - a prompt-injection attempt in the evidence
  - a HIGH SAFE_ACCOUNT or REMOTE_ACCESS_APP flag
RED from `red_min_amount` up, AMBER below it (a scam pattern; DECISIONS 2026-10-11):
  - a HIGH PAY_TO_EARN flag
  - a scam typology with confidence >= red_confidence, and >= red_high_flags HIGH flags or a
    transaction score >= red_txn_score
AMBER:
  - a scam typology with confidence >= amber_confidence
  - any HIGH flag
  - a transaction score >= amber_txn_score_no_evidence when nothing was shared
  - the analysis failed or timed out (needs_review)
GREEN otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.models.schemas import (
    ACTION_FOR_VERDICT,
    EvidenceAnalysis,
    FusionResult,
    IntelResult,
    RedFlag,
    RedFlagCode,
    Severity,
    TxnRisk,
    Verdict,
    WatchlistMatch,
)

MAX_TOP_FLAGS = 4
NOT_SCAM = {"NONE", "UNKNOWN"}
HARD_STOP_FLAGS: dict[RedFlagCode, str] = {
    "SAFE_ACCOUNT": "Asked to move money to a 'safe account'",
    "REMOTE_ACCESS_APP": "Asked to install a remote-access app",
}
_SEVERITY_RANK: dict[Severity, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@dataclass(frozen=True)
class Thresholds:
    red_confidence: float = 0.75
    red_high_flags: int = 2
    red_txn_score: int = 50
    red_min_amount: float = 1000.0
    amber_confidence: float = 0.5
    amber_txn_score_no_evidence: int = 70

    @classmethod
    def from_settings(cls, s: Settings | None = None) -> Thresholds:
        s = s or get_settings()
        return cls(
            red_confidence=s.fusion_red_confidence,
            red_high_flags=s.fusion_red_high_flags,
            red_txn_score=s.fusion_red_txn_score,
            red_min_amount=s.fusion_red_min_amount,
            amber_confidence=s.fusion_amber_confidence,
            amber_txn_score_no_evidence=s.fusion_amber_txn_score_no_evidence,
        )


def _rank(flags: Iterable[RedFlag]) -> list[RedFlag]:
    return sorted(flags, key=lambda f: _SEVERITY_RANK[f.severity])


def _has_high(flags: list[RedFlag], code: RedFlagCode) -> bool:
    return any(f.code == code and f.severity == "HIGH" for f in flags)


def fuse(
    txn: TxnRisk,
    evidence: EvidenceAnalysis | None,
    intel: IntelResult | None,
    *,
    amount: float,
    answer_flags: Iterable[RedFlag] = (),
    analysis_failed: bool = False,
    thresholds: Thresholds | None = None,
) -> FusionResult:
    """The verdict for one check. `analysis_failed` covers a model failure and a timeout."""
    th = thresholds or Thresholds.from_settings()
    flags = _rank([*(evidence.red_flags if evidence else []), *answer_flags])
    high_flags = sum(f.severity == "HIGH" for f in flags)
    typology = evidence.typology_guess if evidence else "UNKNOWN"
    conf = evidence.typology_confidence if evidence else 0.0
    scam_typology = typology not in NOT_SCAM
    matches = intel.watchlist_matches if intel else []
    payee_listed = bool(txn.features and txn.features.watchlist_hit)

    hard_stop = [
        f"{m.type.title()} {m.value} is on the scam watchlist (reported {m.reported_count}x)"
        for m in matches
    ]
    if payee_listed and not any(m.type == "ACCOUNT" for m in matches):
        hard_stop.append("Payee account is on the scam watchlist")
    if evidence and evidence.injection_attempt_detected:
        hard_stop.append("The evidence contains instructions aimed at the screening system")
    hard_stop += [label for code, label in HARD_STOP_FLAGS.items() if _has_high(flags, code)]

    pattern: list[str] = []
    if _has_high(flags, "PAY_TO_EARN"):
        pattern.append("Asked to pay money in order to earn (a job-scam pattern)")
    if (
        scam_typology
        and conf >= th.red_confidence
        and (high_flags >= th.red_high_flags or txn.score >= th.red_txn_score)
    ):
        pattern.append(
            f"Matches a known {typology} scam (confidence {conf:.2f}) with "
            f"{high_flags} high-severity flag(s) and a transaction score of {txn.score}"
        )

    amber: list[str] = []
    if pattern and amount < th.red_min_amount:
        amber.append(
            f"Scam pattern on a payment under S${th.red_min_amount:,.0f}: "
            "pause and explain instead of holding"
        )
    if scam_typology and conf >= th.amber_confidence:
        amber.append(f"Looks like a {typology} scam (confidence {conf:.2f})")
    if high_flags:
        amber.append(f"{high_flags} high-severity red flag(s) in the conversation")
    no_evidence = evidence is None or not evidence.evidence_present
    if no_evidence and txn.score >= th.amber_txn_score_no_evidence:
        amber.append(f"High transaction risk ({txn.score}) and no evidence shared")
    if analysis_failed:
        amber.append("Automatic analysis did not finish; a person needs to review")

    verdict: Verdict
    if hard_stop or (pattern and amount >= th.red_min_amount):
        verdict, reasons = "RED", hard_stop + pattern
    elif amber:
        verdict, reasons = "AMBER", pattern + amber
    else:
        verdict, reasons = "GREEN", ["No scam signals in the conversation or the transaction"]

    return FusionResult(
        verdict=verdict,
        action=ACTION_FOR_VERDICT[verdict],
        reasons=list(dict.fromkeys(reasons)),
        top_flags=top_flags(flags, matches),
        needs_review=analysis_failed,
    )


def top_flags(flags: list[RedFlag], matches: list[WatchlistMatch]) -> list[RedFlag]:
    """Up to 4 flags for the customer screen: evidence flags first (most severe first, so the
    numbered boxes land on the screenshot), then watchlist matches in any slots left."""
    out = flags[:MAX_TOP_FLAGS]
    watch = [
        RedFlag(
            code="WATCHLIST_MATCH",
            severity="HIGH",
            quote=f"{m.value} (reported {m.reported_count} times)",
        )
        for m in matches
    ]
    return out + watch[: MAX_TOP_FLAGS - len(out)]
