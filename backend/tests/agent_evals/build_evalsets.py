# ruff: noqa: E501  (golden-case data: long literal strings read better unwrapped)
"""Builds the ADK eval sets from the golden cases below: 3 per agent (AGENTS_SPEC §8).

    uv --directory backend run python -m tests.agent_evals.build_evalsets

Each case's input is made by the agent's own input builder (the same code the orchestrator
uses), so the eval sets never drift from what the agents really receive. The expected
`final_response` is an expectations object for the custom metric in metrics.py. Everything is
synthetic: phones in +65 8000 01xx, .example domains, Harbour Bank and friends.
Run the evals live with `uv --directory backend run pytest -m live -k agent_evals`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.genai import types

from app.agents import casefile_agent, explainer_agent, intel_agent
from app.agents.evidence_agent import EvidenceItem, EvidenceRequest, build_parts
from app.models.schemas import (
    ClaimedSender,
    Entities,
    EvidenceAnalysis,
    FusionResult,
    IntelResult,
    RedFlag,
    Transfer,
    TxnRisk,
    TxnRiskReason,
    WatchlistMatch,
    WebFinding,
)

HERE = Path(__file__).parent
AGENTS = ("evidence", "intel", "explainer", "casefile")
METRIC = "pauseguard_expectations"
TEST_CONFIG = {
    "criteria": {METRIC: 1.0},
    "custom_metrics": {METRIC: {"code_config": {"name": "tests.agent_evals.metrics.expectations"}}},
}

# --- shared synthetic facts --------------------------------------------------------------

TAN_TRANSFER = Transfer(
    payee_name="Lee Wei Investigation Acct",
    account_number="123-45678-9",
    bank_name="Harbour Bank",
    amount=8000,
    note="case 2231",
)
RAJ_TRANSFER = Transfer(
    payee_name="Ahmad Danial",
    account_number="556-208417-390",
    bank_name="Orchid Trust Bank",
    amount=450,
)
TAN_CHAT = (
    "您好，我是新加坡金融管理局（MAS）调查组的李伟。您的银行户口涉及一宗洗钱案件。"
    "为了保护您的存款，请在今天下午5点前把钱转到金管局的安全账户：Harbour Bank 123-45678-9，"
    "收款人 Lee Wei Investigation Acct。核实链接：https://mas-gov-verify.example/case/2231 。"
    "这是机密调查，不要告诉您的孩子或银行职员，否则您也可能被起诉。"
)
RAJ_CHAT = (
    "Hi Raj! Kelly from TaskStar here. Great job finishing your first 3 tasks, your S$36 "
    "commission is already in your account. You're now eligible for the Gold task set: 20 tasks "
    "at 15% commission each! To unlock it, top up S$450 to your task wallet. It's refundable. "
    "Transfer to our finance colleague: Orchid Trust Bank 556-208417-390, name Ahmad Danial. "
    "Gold slots are limited today."
)
TAN_FLAGS = [
    RedFlag(
        code="SAFE_ACCOUNT", severity="HIGH", quote="把钱转到金管局的安全账户", evidence_index=0
    ),
    RedFlag(
        code="AUTHORITY_CLAIM",
        severity="HIGH",
        quote="我是新加坡金融管理局（MAS）调查组的李伟",
        evidence_index=0,
    ),
    RedFlag(
        code="SECRECY_REQUEST",
        severity="MEDIUM",
        quote="不要告诉您的孩子或银行职员",
        evidence_index=0,
    ),
]
RAJ_FLAGS = [
    RedFlag(
        code="PAY_TO_EARN", severity="HIGH", quote="To unlock it, top up S$450", evidence_index=0
    ),
    RedFlag(
        code="URGENCY", severity="MEDIUM", quote="Gold slots are limited today", evidence_index=0
    ),
]
TAN_MATCHES = [
    WatchlistMatch(type="ACCOUNT", value="123456789", source="SEED", reported_count=4),
    WatchlistMatch(type="PHONE", value="+6580000147", source="SEED", reported_count=6),
]
NOT_CERTAIN = ["you are being scammed", "you're being scammed", "this is a scam", "this is fraud"]
NO_LINKS = ["http", "www.", ".example"]


def _evidence_parts(answer: str, quick: str, pasted: str, transfer: Transfer) -> list[types.Part]:
    return build_parts(
        EvidenceRequest(
            customer_text=answer,
            quick_reply=quick,
            items=[EvidenceItem(text=pasted)],
            transfer=transfer,
        )
    )


def _fusion(verdict: str, flags: list[RedFlag], reasons: list[str], **kw: Any) -> FusionResult:
    action = {"AMBER": "COOL_OFF", "RED": "HOLD_FOR_REVIEW"}[verdict]
    return FusionResult.model_validate(
        {"verdict": verdict, "action": action, "reasons": reasons, "top_flags": flags} | kw
    )


def _analysis(typology: str, conf: float, flags: list[RedFlag], summary: str) -> EvidenceAnalysis:
    return EvidenceAnalysis(
        evidence_present=True,
        summary=summary,
        red_flags=flags,
        typology_guess=typology,  # type: ignore[arg-type]
        typology_confidence=conf,
    )


# --- golden cases: (eval_id, user parts, expectations) -----------------------------------


def evidence_cases() -> list[tuple[str, list[types.Part], dict[str, Any]]]:
    rent = (
        "Hi Aisyah, thanks for signing the tenancy agreement for Blk 210 Bishan St 23 #08-112 "
        "today. As agreed, please pay the deposit of S$3,200 to my account, Kampong Federal Bank "
        "436-905127-318 (Wong Kah Wai). Keys are ready on 1 Nov. Regards, Wong Kah Wai"
    )
    rent_transfer = Transfer(
        payee_name="Wong Kah Wai",
        account_number="436-905127-318",
        bank_name="Kampong Federal Bank",
        amount=3200,
        note="Bishan deposit",
    )
    return [
        (
            "gov_safe_account_zh",
            _evidence_parts(
                "他说他是金管局的官员，要我把钱转到安全账户。", "政府官员", TAN_CHAT, TAN_TRANSFER
            ),
            {
                "typology_guess": "GOV_OFFICIAL_IMPERSONATION",
                "typology_confidence": 0.75,
                "red_flags": [
                    {"code": "SAFE_ACCOUNT", "severity": "HIGH"},
                    {"code": "AUTHORITY_CLAIM"},
                ],
                "injection_attempt_detected": False,
                "$contains": {"entities": ["mas-gov-verify.example"]},
            },
        ),
        (
            "job_pay_to_earn_en",
            _evidence_parts(
                "The recruiter says I must top up to get my commission.",
                "A job recruiter",
                RAJ_CHAT,
                RAJ_TRANSFER,
            ),
            {
                "typology_guess": "JOB_TASK",
                "typology_confidence": 0.75,
                "red_flags": [{"code": "PAY_TO_EARN", "severity": "HIGH"}],
                "injection_attempt_detected": False,
            },
        ),
        (
            "rent_deposit_legit_en",
            _evidence_parts(
                "Deposit for our new flat in Bishan.",
                "No one, it's my own payment",
                rent,
                rent_transfer,
            ),
            {
                "typology_guess": "NONE",
                "injection_attempt_detected": False,
                "$not_contains": {"red_flags": ['"severity": "HIGH"']},
            },
        ),
    ]


def intel_cases() -> list[tuple[str, list[types.Part], dict[str, Any]]]:
    def part(req: intel_agent.IntelRequest) -> list[types.Part]:
        return [types.Part.from_text(text=intel_agent.build_input(req))]

    tan = intel_agent.IntelRequest(
        entities=Entities(
            phones=["+65 8000 0147"],
            urls=["https://mas-gov-verify.example/case/2231"],
            accounts=["123-45678-9"],
            orgs=["MAS"],
            apps=["WhatsApp"],
        ),
        watchlist_matches=TAN_MATCHES,
        typology="GOV_OFFICIAL_IMPERSONATION",
        confidence=0.99,
        claimed_sender=ClaimedSender(name="Lee Wei", claimed_org="MAS", channel="WhatsApp"),
        summary="A man claiming to be an MAS investigator tells the customer to move S$8,000 to a 'safe account'.",
    )
    known = intel_agent.IntelRequest(
        entities=Entities(
            phones=["+65 8000 0112"],
            accounts=["482-19374-2"],
            orgs=["Singapore Police Force"],
            apps=["WhatsApp"],
        ),
        watchlist_matches=[
            WatchlistMatch(type="PHONE", value="+6580000112", source="SEED", reported_count=3)
        ],
        typology="GOV_OFFICIAL_IMPERSONATION",
        confidence=0.9,
        claimed_sender=ClaimedSender(
            name="Inspector Tay", claimed_org="Singapore Police Force", channel="WhatsApp call"
        ),
        summary="A caller claiming to be a police inspector demands a transfer to clear the customer's name.",
    )
    raj = intel_agent.IntelRequest(
        entities=Entities(accounts=["556-208417-390"], orgs=["TaskStar"], apps=["Telegram"]),
        typology="JOB_TASK",
        confidence=0.95,
        claimed_sender=ClaimedSender(name="Kelly", claimed_org="TaskStar", channel="Telegram"),
        summary="A 'TaskStar' recruiter asks for a S$450 top-up to unlock commissions.",
    )
    return [
        (
            "unknown_lookalike_domain",
            part(tan),
            {
                "$tools_called": ["search_agent"],
                "web_findings": [{}],
                "$contains": {"web_findings": ["mas-gov-verify.example"]},
                "$max_items": {"web_findings": 2},
            },
        ),
        (
            "nothing_unknown_to_search",
            part(known),
            {"$tools_not_called": ["search_agent"], "$max_items": {"web_findings": 0}},
        ),
        (
            "unknown_job_platform",
            part(raj),
            {
                "$tools_called": ["search_agent"],
                "$contains": {"web_findings": ["TaskStar"]},
                "$max_items": {"web_findings": 2},
            },
        ),
    ]


def explainer_cases() -> list[tuple[str, list[types.Part], dict[str, Any]]]:
    def part(req: explainer_agent.ExplainRequest) -> list[types.Part]:
        return [types.Part.from_text(text=explainer_agent.build_input(req))]

    red = _fusion(
        "RED",
        TAN_FLAGS,
        [
            "Account 123456789 is on the scam watchlist (reported 4x)",
            "Asked to move money to a 'safe account'",
        ],
    )
    amber_job = _fusion(
        "AMBER",
        RAJ_FLAGS,
        [
            "Asked to pay money in order to earn (a job-scam pattern)",
            "Scam pattern on a payment under S$1,000: pause and explain instead of holding",
        ],
    )
    friend_flags = [
        RedFlag(
            code="NEW_NUMBER_FRIEND",
            severity="MEDIUM",
            quote="Hi Uncle, it's me Wei Ming, this is my new number",
        ),
        RedFlag(code="URGENCY", severity="HIGH", quote="I need S$1,500 today, please, very urgent"),
    ]
    amber_friend = _fusion(
        "AMBER",
        friend_flags,
        [
            "Looks like a FAKE_FRIEND scam (confidence 0.80)",
            "1 high-severity red flag(s) in the conversation",
        ],
    )
    return [
        (
            "red_gov_zh_senior",
            part(
                explainer_agent.ExplainRequest(
                    red, "zh", "GOV_OFFICIAL_IMPERSONATION", 67, "Tan Jun Hao (son)"
                )
            ),
            {
                "$language": "zh",
                "$max_len": {"headline": 16, "body": 120},
                "$contains": {"*": ["暂停"]},
                "$not_contains": {"*": NO_LINKS},
            },
        ),
        (
            "amber_job_en",
            part(
                explainer_agent.ExplainRequest(
                    amber_job, "en", "JOB_TASK", 29, "Priya Kumar (sister)"
                )
            ),
            {
                "$language": "en",
                "$max_len": {"headline": 8, "body": 60},
                "$not_contains": {"*": NOT_CERTAIN + NO_LINKS},
            },
        ),
        (
            "amber_fake_friend_en_senior",
            part(explainer_agent.ExplainRequest(amber_friend, "en", "FAKE_FRIEND", 72, None)),
            {
                "$language": "en",
                "$max_len": {"headline": 8, "body": 60},
                "$not_contains": {"*": NOT_CERTAIN + NO_LINKS},
            },
        ),
    ]


def casefile_cases() -> list[tuple[str, list[types.Part], dict[str, Any]]]:
    def part(req: casefile_agent.CaseFileRequest) -> list[types.Part]:
        return [types.Part.from_text(text=casefile_agent.build_input(req))]

    tan_txn = TxnRisk(
        score=100,
        reasons=[
            TxnRiskReason(code="NEW_PAYEE", label="First transfer to this account", points=20),
            TxnRiskReason(
                code="AMOUNT_SPIKE", label="Amount is 40x the usual 90-day payment", points=30
            ),
            TxnRiskReason(
                code="WATCHLIST_MATCH", label="Payee account is on the scam watchlist", points=40
            ),
        ],
    )
    tan = casefile_agent.CaseFileRequest(
        transfer=TAN_TRANSFER,
        txn=tan_txn,
        fusion=_fusion(
            "RED",
            TAN_FLAGS[:2],
            [
                "Account 123456789 is on the scam watchlist (reported 4x)",
                "Asked to move money to a 'safe account'",
            ],
        ),
        evidence=_analysis(
            "GOV_OFFICIAL_IMPERSONATION",
            0.99,
            TAN_FLAGS,
            "A man claiming to be an MAS investigator tells the customer to move S$8,000 to a 'safe account' and keep it secret.",
        ),
        intel=IntelResult(
            watchlist_matches=TAN_MATCHES,
            web_findings=[
                WebFinding(
                    query="mas-gov-verify.example (claims to be MAS)",
                    finding="No trace of this domain; MAS's official website is mas.gov.sg.",
                    risk="HIGH",
                )
            ],
        ),
        customer_text="他说他是金管局的官员，要我把钱转到安全账户。",
        quick_reply="政府官员",
    )
    raj = casefile_agent.CaseFileRequest(
        transfer=RAJ_TRANSFER,
        txn=TxnRisk(
            score=55,
            reasons=[
                TxnRiskReason(code="NEW_PAYEE", label="First transfer to this account", points=20),
                TxnRiskReason(
                    code="AMOUNT_SPIKE", label="Amount is 12x the usual 90-day payment", points=30
                ),
            ],
        ),
        fusion=_fusion(
            "AMBER",
            RAJ_FLAGS,
            [
                "Asked to pay money in order to earn (a job-scam pattern)",
                "Scam pattern on a payment under S$1,000: pause and explain instead of holding",
            ],
        ),
        evidence=_analysis(
            "JOB_TASK",
            0.95,
            RAJ_FLAGS,
            "A 'TaskStar' recruiter on Telegram asks for a S$450 top-up to unlock commissions, paid to a personal account.",
        ),
        intel=IntelResult(),
        customer_text="The recruiter says I must top up to get my commission.",
        quick_reply="A job recruiter",
    )
    failed = casefile_agent.CaseFileRequest(
        transfer=Transfer(payee_name="Goh Siew Ling", account_number="771-204593-118", amount=2400),
        txn=TxnRisk(
            score=75,
            reasons=[
                TxnRiskReason(code="NEW_PAYEE", label="First transfer to this account", points=20),
                TxnRiskReason(
                    code="AMOUNT_SPIKE", label="Amount is 15x the usual 90-day payment", points=30
                ),
            ],
        ),
        fusion=_fusion(
            "AMBER",
            [],
            ["Automatic analysis did not finish; a person needs to review"],
            needs_review=True,
        ),
        evidence=None,
        intel=IntelResult(),
        customer_text="For my friend.",
        quick_reply="A friend or family member",
    )
    return [
        (
            "red_gov_watchlist",
            part(tan),
            {
                "$one_of": {"recommended_action": ["HOLD", "REPORT_SCAM", "ESCALATE"]},
                "confidence": 0.8,
                "evidence_points": [{"flag": "SAFE_ACCOUNT"}],
                "$max_len": {"title": 10},
                "$contains": {"summary": ["MAS"]},
            },
        ),
        (
            "amber_job_task",
            part(raj),
            {
                "$one_of": {"recommended_action": ["HOLD", "ESCALATE", "REPORT_SCAM"]},
                "evidence_points": [{"flag": "PAY_TO_EARN"}],
                "$max_len": {"title": 10},
            },
        ),
        (
            "amber_analysis_failed",
            part(failed),
            {
                "$one_of": {"recommended_action": ["ESCALATE", "HOLD"]},
                "$max_len": {"title": 10},
                "$max_items": {"evidence_points": 0},
            },
        ),
    ]


CASES = {
    "evidence": evidence_cases,
    "intel": intel_cases,
    "explainer": explainer_cases,
    "casefile": casefile_cases,
}


def eval_set(agent: str) -> dict[str, Any]:
    cases = []
    for eval_id, parts, expect in CASES[agent]():
        cases.append(
            {
                "eval_id": eval_id,
                "conversation": [
                    {
                        "invocation_id": f"{agent}-{eval_id}",
                        "user_content": {
                            "role": "user",
                            "parts": [p.model_dump(exclude_none=True) for p in parts],
                        },
                        "final_response": {
                            "role": "model",
                            "parts": [{"text": json.dumps(expect, ensure_ascii=False)}],
                        },
                    }
                ],
                "session_input": {"app_name": "pauseguard", "user_id": "eval", "state": {}},
            }
        )
    return {
        "eval_set_id": f"{agent}_golden",
        "name": f"{agent} agent: golden cases",
        "description": "Built by tests/agent_evals/build_evalsets.py; expectations per metrics.py.",
        "eval_cases": cases,
    }


def render(agent: str) -> dict[str, str]:
    """File name -> content, for one agent's folder."""
    return {
        f"{agent}.test.json": json.dumps(eval_set(agent), ensure_ascii=False, indent=2) + "\n",
        "test_config.json": json.dumps(TEST_CONFIG, indent=2) + "\n",
    }


def main() -> None:
    for agent in AGENTS:
        for name, content in render(agent).items():
            (HERE / agent / name).write_text(content, encoding="utf-8")
            print(f"wrote tests/agent_evals/{agent}/{name}")


if __name__ == "__main__":
    main()
