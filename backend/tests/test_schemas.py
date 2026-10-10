"""The schemas accept the example payloads written in docs/AGENTS_SPEC.md and docs/API_SPEC.md."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    CheckMessageRequest,
    CheckMessageResponse,
    CreateCheckRequest,
    CreateCheckResponse,
    DecisionRequest,
    EvidenceAnalysis,
    IntelResult,
    MetricsResponse,
    RedFlag,
    SignUploadRequest,
)


def test_evidence_analysis_spec_example():
    ev = EvidenceAnalysis.model_validate(
        {
            "evidence_present": True,
            "summary": "Chat from someone claiming to be an MAS officer ...",
            "claimed_sender": {
                "name": "Officer Lim",
                "claimed_org": "Monetary Authority of Singapore",
                "channel": "WhatsApp",
            },
            "payment_instruction": {
                "amount": 8000,
                "account": "123-45678-9",
                "reason_given": "safe account for investigation",
            },
            "entities": {
                "phones": ["+65 8000 0123"],
                "urls": [],
                "accounts": ["123-45678-9"],
                "orgs": ["MAS"],
                "apps": [],
            },
            "red_flags": [
                {
                    "code": "AUTHORITY_CLAIM",
                    "severity": "HIGH",
                    "quote": "This is Officer Lim from MAS",
                    "evidence_index": 0,
                    "box_2d": [120, 40, 180, 900],
                }
            ],
            "typology_guess": "GOV_OFFICIAL_IMPERSONATION",
            "typology_confidence": 0.92,
            "language_detected": "en",
            "injection_attempt_detected": False,
        }
    )
    assert ev.red_flags[0].box_2d == [120, 40, 180, 900]


@pytest.mark.parametrize(
    "box",
    [[0, 0, 1001, 10], [10, 10, 5, 20], [1, 2, 3], [-1, 0, 10, 10]],
)
def test_invalid_box_is_dropped_not_rejected(box):
    flag = RedFlag(code="URGENCY", severity="MEDIUM", quote="act now", box_2d=box)
    assert flag.box_2d is None


def test_unknown_red_flag_code_is_rejected():
    with pytest.raises(ValidationError):
        RedFlag(code="MADE_UP", severity="HIGH", quote="x")


def test_evidence_max_six_flags():
    flag = {"code": "URGENCY", "severity": "LOW", "quote": "now"}
    with pytest.raises(ValidationError):
        EvidenceAnalysis(evidence_present=True, summary="s", red_flags=[flag] * 7)


def test_intel_result_shape():
    IntelResult.model_validate(
        {
            "watchlist_matches": [
                {"type": "PHONE", "value": "+6580000123", "source": "SEED", "reported_count": 3}
            ],
            "web_findings": [
                {
                    "query": "mas-gov-verify.example",
                    "finding": "Reported as a phishing site.",
                    "sources": ["https://example.com/a"],
                    "risk": "HIGH",
                }
            ],
        }
    )


def test_create_check_request_and_both_responses():
    CreateCheckRequest.model_validate(
        {
            "customer_id": "cust_001",
            "transfer": {
                "payee_name": "Lee Wei Investigation Acct",
                "account_number": "123-45678-9",
                "bank_name": "Harbour Bank",
                "dest_type": "LOCAL_BANK",
                "amount": 8000,
                "currency": "SGD",
                "note": "case 2231",
            },
            "language": "zh",
        }
    )
    CreateCheckResponse.model_validate(
        {
            "check_id": "chk_01J",
            "status": "CHECKIN",
            "txn_risk": {
                "score": 65,
                "reasons": [
                    {"code": "NEW_PAYEE", "label": "First payment to this account", "points": 20}
                ],
            },
            "question": {
                "text": "这笔转账是谁让您付的？",
                "quick_replies": ["A government officer"],
            },
        }
    )
    CreateCheckResponse.model_validate(
        {
            "check_id": "chk_02",
            "status": "DONE",
            "verdict": "GREEN",
            "customer_message": {
                "language": "en",
                "headline": "Looks good",
                "body": "Your transfer is on its way.",
            },
        }
    )


def test_message_request_max_three_files():
    CheckMessageRequest(text="hi", evidence_uris=["gs://b/1", "gs://b/2", "gs://b/3"])
    with pytest.raises(ValidationError):
        CheckMessageRequest(evidence_uris=["gs://b/x"] * 4)


def test_check_message_response_spec_example():
    resp = CheckMessageResponse.model_validate(
        {
            "check_id": "chk_01",
            "status": "DONE",
            "verdict": "RED",
            "action": "HOLD_FOR_REVIEW",
            "needs_review": False,
            "typology": "GOV_OFFICIAL_IMPERSONATION",
            "confidence": 0.93,
            "top_flags": [
                {
                    "code": "SAFE_ACCOUNT",
                    "severity": "HIGH",
                    "quote": "transfer to the safe account",
                    "evidence_index": 0,
                    "box_2d": [410, 60, 470, 940],
                }
            ],
            "customer_message": {
                "language": "zh",
                "headline": "h",
                "body": "b",
                "flag_explanations": [{"code": "SAFE_ACCOUNT", "text": "t"}],
                "next_steps": ["Call 1799"],
            },
            "case_id": "case_01",
            "latency_ms": {"total": 4210},
        }
    )
    assert resp.latency_ms.total == 4210


def test_upload_rejects_unsupported_type():
    with pytest.raises(ValidationError):
        SignUploadRequest(check_id="c", filename="a.exe", content_type="application/x-msdownload")


def test_decision_and_metrics():
    DecisionRequest(action="REPORT_SCAM", note="Called customer")
    MetricsResponse.model_validate(
        {
            "checks": 312,
            "verdicts": {"GREEN": 240, "AMBER": 51, "RED": 21},
            "money_protected_sgd": 184500,
            "false_positive_rate": 0.048,
            "latency_ms": {"p50": 3900, "p95": 8100},
            "top_typologies": [{"typology": "JOB_TASK", "count": 19}],
            "cost_per_check_usd": 0.0041,
        }
    )
