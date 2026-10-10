"""Fusion policy: every rule of AGENTS_SPEC §4 (plus the proportionality rule), each threshold
edge, and the top-flag selection. `make test` enforces 100% branch coverage of app/policy."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.models.schemas import (
    EvidenceAnalysis,
    IntelResult,
    RedFlag,
    TxnFeatures,
    TxnRisk,
    WatchlistMatch,
)
from app.policy.fusion import MAX_TOP_FLAGS, Thresholds, fuse, top_flags

TH = Thresholds()  # the spec defaults, independent of any .env


def txn(score: int = 20, *, payee_listed: bool = False) -> TxnRisk:
    features = TxnFeatures(
        is_new_payee=True, dest_type="LOCAL_BANK", hour_local=14, watchlist_hit=payee_listed
    )
    return TxnRisk(score=score, features=features)


def flag(code: str, severity: str = "HIGH", **kw: Any) -> RedFlag:
    return RedFlag.model_validate({"code": code, "severity": severity, "quote": f"q {code}"} | kw)


def ev(
    typology: str = "NONE",
    conf: float = 0.9,
    flags: list[RedFlag] | None = None,
    *,
    present: bool = True,
    injection: bool = False,
) -> EvidenceAnalysis:
    return EvidenceAnalysis(
        evidence_present=present,
        summary="s",
        red_flags=flags or [],
        typology_guess=typology,  # type: ignore[arg-type]
        typology_confidence=conf,
        injection_attempt_detected=injection,
    )


def match(type_: str = "PHONE", value: str = "+6580000147", n: int = 6) -> WatchlistMatch:
    return WatchlistMatch.model_validate(
        {"type": type_, "value": value, "source": "SEED", "reported_count": n}
    )


def run(
    t: TxnRisk | None = None,
    e: EvidenceAnalysis | None = None,
    i: IntelResult | None = None,
    *,
    amount: float = 5000,
    **kw: Any,
) -> Any:
    return fuse(t or txn(), e, i, amount=amount, thresholds=kw.pop("thresholds", TH), **kw)


# --- RED: hard-stop signals, at any amount -------------------------------------------------


def test_watchlist_match_in_intel_is_red_even_for_a_small_legit_looking_payment() -> None:
    r = run(e=ev("NONE", 0.95), i=IntelResult(watchlist_matches=[match()]), amount=50)
    assert r.verdict == "RED" and r.action == "HOLD_FOR_REVIEW" and not r.needs_review
    assert r.reasons == ["Phone +6580000147 is on the scam watchlist (reported 6x)"]
    assert [f.code for f in r.top_flags] == ["WATCHLIST_MATCH"]


def test_payee_account_on_watchlist_without_intel_is_red() -> None:
    r = run(txn(60, payee_listed=True), ev("NONE"), None, amount=10)
    assert r.verdict == "RED"
    assert r.reasons == ["Payee account is on the scam watchlist"]


def test_payee_account_reason_is_not_repeated_when_intel_has_the_account_match() -> None:
    i = IntelResult(watchlist_matches=[match("ACCOUNT", "123456789", 4)])
    r = run(txn(100, payee_listed=True), ev("NONE"), i)
    assert r.reasons == ["Account 123456789 is on the scam watchlist (reported 4x)"]


def test_injection_is_red() -> None:
    r = run(e=ev("NONE", 0.9, [flag("COACHING_TO_LIE")], injection=True), amount=100)
    assert r.verdict == "RED"
    assert "instructions aimed at the screening system" in r.reasons[0]


@pytest.mark.parametrize("code", ["SAFE_ACCOUNT", "REMOTE_ACCESS_APP"])
def test_hard_stop_flags_are_red_at_any_amount(code: str) -> None:
    r = run(e=ev("UNKNOWN", 0.3, [flag(code)]), amount=20)
    assert r.verdict == "RED"


def test_hard_stop_flag_below_high_is_not_a_hard_stop() -> None:
    r = run(e=ev("NONE", 0.9, [flag("SAFE_ACCOUNT", "MEDIUM")]))
    assert r.verdict == "GREEN"


# --- scam patterns: RED from red_min_amount, AMBER below -----------------------------------


def test_pay_to_earn_holds_a_large_payment() -> None:
    r = run(e=ev("JOB_TASK", 0.4, [flag("PAY_TO_EARN")]), amount=1000)
    assert r.verdict == "RED"
    assert r.reasons == ["Asked to pay money in order to earn (a job-scam pattern)"]


def test_pay_to_earn_pauses_a_small_payment() -> None:
    r = run(e=ev("JOB_TASK", 0.4, [flag("PAY_TO_EARN")]), amount=999.99)
    assert r.verdict == "AMBER" and r.action == "COOL_OFF"
    assert r.reasons[0].startswith("Asked to pay money in order to earn")
    assert "under S$1,000" in r.reasons[1]


def test_confident_typology_with_two_high_flags_is_red() -> None:
    flags = [flag("AUTHORITY_CLAIM"), flag("SECRECY_REQUEST")]
    r = run(txn(10), ev("INVESTMENT", 0.75, flags))
    assert r.verdict == "RED"
    assert "INVESTMENT" in r.reasons[0] and "2 high-severity" in r.reasons[0]


def test_confident_typology_with_high_txn_score_is_red() -> None:
    r = run(txn(50), ev("ROMANCE", 0.8))
    assert r.verdict == "RED"


def test_confident_typology_without_flags_or_txn_risk_is_amber() -> None:
    r = run(txn(49), ev("ROMANCE", 0.95, [flag("URGENCY", "MEDIUM")]))
    assert r.verdict == "AMBER"
    assert r.reasons == ["Looks like a ROMANCE scam (confidence 0.95)"]


def test_typology_just_below_red_confidence_is_amber() -> None:
    r = run(txn(90), ev("PHISHING", 0.74, [flag("SUSPICIOUS_URL"), flag("URGENCY")]))
    assert r.verdict == "AMBER"


def test_raj_demo_shape_is_amber() -> None:
    """S$450, JOB_TASK 0.95, one HIGH PAY_TO_EARN, txn 55: a pattern, but under S$1,000."""
    flags = [flag("PAY_TO_EARN"), flag("OFF_PLATFORM_PAYMENT", "MEDIUM"), flag("URGENCY", "LOW")]
    r = run(txn(55), ev("JOB_TASK", 0.95, flags), IntelResult(), amount=450)
    assert r.verdict == "AMBER" and not r.needs_review


def test_red_min_amount_zero_restores_the_spec_as_written() -> None:
    th = Thresholds(red_min_amount=0)
    r = run(txn(55), ev("JOB_TASK", 0.95, [flag("PAY_TO_EARN")]), amount=450, thresholds=th)
    assert r.verdict == "RED"


# --- AMBER -----------------------------------------------------------------------------------


def test_moderate_typology_confidence_is_amber() -> None:
    assert run(txn(10), ev("ECOMMERCE", 0.5)).verdict == "AMBER"


def test_low_typology_confidence_is_green() -> None:
    assert run(txn(10), ev("ECOMMERCE", 0.49)).verdict == "GREEN"


def test_one_high_flag_is_amber() -> None:
    r = run(txn(10), ev("NONE", 0.9, [flag("URGENCY")]))
    assert r.verdict == "AMBER"
    assert r.reasons == ["1 high-severity red flag(s) in the conversation"]


@pytest.mark.parametrize("evidence", [None, ev("NONE", 0.9, present=False)])
def test_high_txn_score_with_nothing_shared_is_amber(evidence: EvidenceAnalysis | None) -> None:
    r = run(txn(70), evidence)
    assert r.verdict == "AMBER"
    assert r.reasons == ["High transaction risk (70) and no evidence shared"]


def test_high_txn_score_with_reassuring_evidence_is_green() -> None:
    assert run(txn(95), ev("NONE", 0.95)).verdict == "GREEN"


def test_txn_score_just_below_the_no_evidence_threshold_is_green() -> None:
    assert run(txn(69), None).verdict == "GREEN"


def test_failed_analysis_is_amber_with_review_never_green() -> None:
    r = run(txn(10), ev("UNKNOWN", 0.0), analysis_failed=True)
    assert r.verdict == "AMBER" and r.needs_review
    assert r.reasons == ["Automatic analysis did not finish; a person needs to review"]


def test_failed_analysis_keeps_a_hard_stop_red() -> None:
    r = run(txn(10), None, IntelResult(watchlist_matches=[match()]), analysis_failed=True)
    assert r.verdict == "RED" and r.needs_review


# --- GREEN, inputs and outputs -------------------------------------------------------------


def test_aisyah_demo_shape_is_green() -> None:
    r = run(txn(55), ev("NONE", 0.95), IntelResult(), amount=3200)
    assert r.verdict == "GREEN" and r.action == "PROCEED" and r.top_flags == []
    assert r.reasons == ["No scam signals in the conversation or the transaction"]


def test_no_evidence_and_no_intel_with_low_txn_is_green() -> None:
    assert run(txn(30), None, None).verdict == "GREEN"


def test_answer_flags_count_like_evidence_flags() -> None:
    r = run(txn(10), ev("NONE", 0.9), answer_flags=[flag("AUTHORITY_CLAIM")])
    assert r.verdict == "AMBER"
    assert [f.code for f in r.top_flags] == ["AUTHORITY_CLAIM"]


def test_reasons_are_unique_and_red_lists_hard_stops_then_patterns() -> None:
    i = IntelResult(watchlist_matches=[match(), match()])
    r = run(txn(80), ev("GOV_OFFICIAL_IMPERSONATION", 0.99, [flag("SAFE_ACCOUNT")]), i)
    assert r.reasons[0].startswith("Phone +6580000147")
    assert r.reasons[1] == "Asked to move money to a 'safe account'"
    assert r.reasons[2].startswith("Matches a known GOV_OFFICIAL_IMPERSONATION scam")
    assert len(r.reasons) == len(set(r.reasons)) == 3


def test_top_flags_are_most_severe_first_and_capped() -> None:
    flags = [
        flag("URGENCY", "LOW"),
        flag("AUTHORITY_CLAIM", "HIGH", box_2d=[1, 2, 3, 4], evidence_index=0),
        flag("THREAT_OR_FEAR", "MEDIUM"),
        flag("SAFE_ACCOUNT", "HIGH"),
        flag("SECRECY_REQUEST", "HIGH"),
    ]
    r = run(
        e=ev("GOV_OFFICIAL_IMPERSONATION", 0.99, flags), i=IntelResult(watchlist_matches=[match()])
    )
    codes = [f.code for f in r.top_flags]
    assert codes == ["AUTHORITY_CLAIM", "SAFE_ACCOUNT", "SECRECY_REQUEST", "THREAT_OR_FEAR"]
    assert len(r.top_flags) == MAX_TOP_FLAGS
    assert r.top_flags[0].box_2d == [1, 2, 3, 4]


def test_watchlist_matches_fill_the_free_top_flag_slots() -> None:
    out = top_flags([flag("URGENCY")], [match(), match("URL", "x.example/a", 2), match(), match()])
    assert [f.code for f in out] == ["URGENCY"] + ["WATCHLIST_MATCH"] * 3
    assert out[1].quote == "+6580000147 (reported 6 times)"


def test_thresholds_come_from_settings() -> None:
    s = Settings(  # type: ignore[call-arg]
        _env_file=None,
        fusion_red_confidence=0.8,
        fusion_red_high_flags=3,
        fusion_red_txn_score=60,
        fusion_red_min_amount=0,
        fusion_amber_confidence=0.6,
        fusion_amber_txn_score_no_evidence=80,
    )
    assert Thresholds.from_settings(s) == Thresholds(0.8, 3, 60, 0, 0.6, 80)


def test_default_thresholds_match_the_config_defaults() -> None:
    assert Thresholds.from_settings(Settings(_env_file=None)) == TH  # type: ignore[call-arg]


def test_fuse_reads_settings_when_no_thresholds_are_given() -> None:
    r = fuse(txn(10), ev("NONE"), None, amount=100)
    assert r.verdict == "GREEN"
