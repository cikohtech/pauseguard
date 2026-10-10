"""Pydantic models for the eval set (DATA_SPEC §4): a planned slot, a draft and a final case.

Imported by make_eval_messages.py, render_chats.py, the backend tests and the phase 09 benchmark,
so the shapes are written down once.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Label = Literal["SCAM", "LEGIT"]
ScamTypology = Literal[
    "GOV_OFFICIAL_IMPERSONATION",
    "INVESTMENT",
    "JOB_TASK",
    "PHISHING",
    "ECOMMERCE",
    "FAKE_FRIEND",
    "ROMANCE",
    "BEC_INVOICE",
]
LegitKind = Literal[
    "RENT_DEPOSIT",
    "NEW_CONTRACTOR",
    "FAMILY_REQUEST",
    "BANK_SMS",
    "INVOICE",
    "BROKER_TOPUP",
    "CHARITY",
    "BILL_SPLIT",
    "TUITION",
    "FRIEND_NEW_NUMBER",
]
Language = Literal["en", "zh"]
# chat/sms/email are rendered to PNG screenshots, pdf to a one-page PDF, text is pasted text.
Format = Literal["chat", "sms", "email", "text", "pdf", "none"]
IMAGE_FORMATS = ("chat", "sms", "email")
Difficulty = Literal["obvious", "subtle"]
Split = Literal["dev", "test"]
DestType = Literal["LOCAL_BANK", "OVERSEAS", "CRYPTO_EXCHANGE", "MERCHANT", "PAYNOW"]
Verdict = Literal["GREEN", "AMBER", "RED"]
QuickReply = Literal[
    "A government officer",
    "A job recruiter",
    "An investment group",
    "A friend or family member",
    "A seller",
    "No one, it's my own payment",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Plan ---------------------------------------------------------------------------------------


class FixedPayee(Strict):
    """An existing payee of the customer (is_new_payee = false), taken from data/seed/payees.csv."""

    payee_name: str
    account_number: str
    bank_name: str
    dest_type: DestType


class Slot(Strict):
    id: str
    split: Split
    label: Label
    scenario: str  # a ScamTypology for SCAM, a LegitKind for LEGIT
    language: Language
    format: Format
    difficulty: Difficulty
    injection: bool = False
    customer_id: str
    customer_name: str
    customer_age: int
    customer_segment: str
    contact_phone: str  # the scammer's or legit counterpart's number, if the story needs one
    is_new_payee: bool
    fixed_payee: FixedPayee | None = None


# --- Draft (what the drafter writes for a slot) -------------------------------------------------


class Bubble(Strict):
    who: Literal["them", "me", "day"]  # "day" is a date separator such as "Yesterday"
    time: str | None = None
    text: str = Field(min_length=1)


class Header(Strict):
    name: str
    subtitle: str | None = None


class Email(Strict):
    from_name: str
    from_addr: str
    to: str
    subject: str
    date: str
    body: list[str] = Field(min_length=1)
    footer: list[str] = Field(default_factory=list)  # small grey print (and injection text)


class DocItem(Strict):
    description: str
    amount: float | None = None


class Document(Strict):
    kind: str  # invoice, letter, tenancy, quotation, receipt, certificate, contract, notice
    issuer: str
    issuer_lines: list[str] = Field(default_factory=list)  # address, UEN, licence no.
    title: str
    ref: str | None = None
    date: str
    to_lines: list[str] = Field(default_factory=list)
    body: list[str] = Field(default_factory=list)
    items: list[DocItem] = Field(default_factory=list)
    total: float | None = None
    payment: dict[str, str] = Field(default_factory=dict)  # bank, account name, account no, ref
    footer: list[str] = Field(default_factory=list)
    signature: str | None = None


class Evidence(Strict):
    format: Format
    header: Header | None = None
    messages: list[Bubble] = Field(default_factory=list)
    email: Email | None = None
    document: Document | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _shape_matches_format(self) -> Evidence:
        need = {
            "chat": self.header is not None and len(self.messages) >= 2,
            "sms": self.header is not None and len(self.messages) >= 1,
            "email": self.email is not None,
            "pdf": self.document is not None,
            "text": bool(self.text),
            "none": not (self.messages or self.email or self.document or self.text),
        }[self.format]
        if not need:
            raise ValueError(f"evidence shape does not match format {self.format!r}")
        return self


class TransferDraft(Strict):
    payee_name: str = Field(min_length=1, max_length=120)
    account_number: str = Field(min_length=1, max_length=40)
    bank_name: str
    dest_type: DestType
    amount: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=140)


class Draft(Strict):
    difficulty: Difficulty
    evidence: Evidence
    customer_answer: str = Field(min_length=1)
    quick_reply: QuickReply | None = None  # None: the customer typed an answer, no chip
    transfer: TransferDraft
    reviewer_note: str = Field(min_length=1)


class DraftRecord(Strict):
    """One line of data/eval/drafts.jsonl: the slot plus its draft."""

    slot: Slot
    draft: Draft
    drafter: str  # "library" (hand-written, see DECISIONS.md) or the Gemini model ID


# --- Final case (data/eval/cases.jsonl) ---------------------------------------------------------


class CaseTransfer(Strict):
    customer_id: str
    payee_name: str
    account_number: str
    bank_name: str
    dest_type: DestType
    amount: float
    currency: Literal["SGD"] = "SGD"
    note: str | None = None
    is_new_payee: bool


class CaseEvidence(Strict):
    type: Literal["image", "pdf", "text"]
    style: Literal["chat", "sms", "email", "document", "text"]
    path: str | None = None  # repo-relative, for image and pdf
    text: str | None = None  # for text


class EvalCase(Strict):
    id: str
    split: Split
    label: Label
    typology: str  # the scam typology, or "NONE" for LEGIT
    scenario: str  # typology for SCAM, legit kind for LEGIT
    language: Language
    difficulty: Difficulty
    injection: bool
    transfer: CaseTransfer
    customer_answer: str
    quick_reply: QuickReply | None = None  # None: the customer typed an answer, no chip
    evidence: list[CaseEvidence]
    expected_verdict_min: Verdict
