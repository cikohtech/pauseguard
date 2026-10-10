"""The three demo scenarios (docs/DEMO_SCRIPT.md, data/demo/README.md), defined once.

Used by the orchestrator CLI now, and by `make smoke` and /admin/selftest later (phase 10).
Evidence paths are repo-relative local files (local dev); in cloud they become gs:// URIs.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import REPO_ROOT
from app.models.schemas import (
    CheckMessageRequest,
    CreateCheckRequest,
    Language,
    Transfer,
    Verdict,
)


@dataclass(frozen=True)
class Scenario:
    key: str
    customer_id: str
    language: Language
    transfer: Transfer
    answer: str
    quick_reply: str
    evidence_uris: tuple[str, ...] = ()
    pasted_file: str | None = None  # a .txt the customer pastes as text evidence
    expected: tuple[Verdict, ...] = ()

    def create_request(self) -> CreateCheckRequest:
        return CreateCheckRequest(
            customer_id=self.customer_id, transfer=self.transfer, language=self.language
        )

    def message(self, evidence_uris: tuple[str, ...] | None = None) -> CheckMessageRequest:
        pasted = None
        if self.pasted_file:
            pasted = (REPO_ROOT / self.pasted_file).read_text(encoding="utf-8").strip()
        return CheckMessageRequest(
            text=self.answer,
            quick_reply=self.quick_reply,
            evidence_uris=list(self.evidence_uris if evidence_uris is None else evidence_uris),
            pasted_text=pasted,
        )


SCENARIOS: dict[str, Scenario] = {
    "tan": Scenario(
        key="tan",
        customer_id="cust_001",
        language="zh",
        transfer=Transfer(
            payee_name="Lee Wei Investigation Acct",
            account_number="123-45678-9",
            bank_name="Harbour Bank",
            dest_type="LOCAL_BANK",
            amount=8000,
            note="case 2231",
        ),
        answer="他说他是金管局的官员，我的账户涉及洗钱，要我把钱转到安全账户。",
        quick_reply="政府官员",
        evidence_uris=("data/demo/tan_mas_chat.png",),
        expected=("RED",),
    ),
    "raj": Scenario(
        key="raj",
        customer_id="cust_002",
        language="en",
        transfer=Transfer(
            payee_name="Ahmad Danial",
            account_number="556-208417-390",
            bank_name="Orchid Trust Bank",
            dest_type="LOCAL_BANK",
            amount=450,
        ),
        answer="The recruiter says I need to top up to unlock my commission. Here is the message.",
        quick_reply="A job recruiter",
        pasted_file="data/demo/raj_job_chat.txt",
        expected=("AMBER", "RED"),
    ),
    "aisyah": Scenario(
        key="aisyah",
        customer_id="cust_003",
        language="en",
        transfer=Transfer(
            payee_name="Wong Kah Wai",
            account_number="436-905127-318",
            bank_name="Kampong Federal Bank",
            dest_type="LOCAL_BANK",
            amount=3200,
            note="Bishan deposit",
        ),
        answer="It's the deposit for the flat we're renting in Bishan. Tenancy agreement attached.",
        quick_reply="No one, it's my own payment",
        evidence_uris=("data/demo/aisyah_tenancy.pdf",),
        expected=("GREEN",),
    ),
}
