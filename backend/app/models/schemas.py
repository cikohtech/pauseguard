"""Pydantic models shared by the API and the agents.

Sources: docs/AGENTS_SPEC.md (enums + agent I/O) and docs/API_SPEC.md (REST contracts),
with Firestore document shapes from docs/DATA_SPEC.md §3. Every LLM call is validated
against one of the agent output models below.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Shared enums (AGENTS_SPEC §0)
# ---------------------------------------------------------------------------

Verdict = Literal["GREEN", "AMBER", "RED"]
Action = Literal["PROCEED", "COOL_OFF", "HOLD_FOR_REVIEW"]
Typology = Literal[
    "GOV_OFFICIAL_IMPERSONATION",  # fake police/MAS/MOM/bank officer, "safe account"
    "INVESTMENT",  # fake platform, guaranteed returns, crypto
    "JOB_TASK",  # pay to unlock tasks / commissions
    "PHISHING",  # fake parcel/bank link, credential capture
    "ECOMMERCE",  # fake seller, pay first
    "ROMANCE",  # online partner needs money
    "FAKE_FRIEND",  # "guess who", new number, urgent loan
    "BEC_INVOICE",  # changed bank details on invoice
    "NONE",
    "UNKNOWN",
]
RedFlagCode = Literal[
    "AUTHORITY_CLAIM",
    "URGENCY",
    "SECRECY_REQUEST",
    "SAFE_ACCOUNT",
    "GUARANTEED_RETURNS",
    "UPFRONT_FEE",
    "PAY_TO_EARN",
    "OFF_PLATFORM_PAYMENT",
    "REMOTE_ACCESS_APP",
    "SUSPICIOUS_URL",
    "NEW_NUMBER_FRIEND",
    "CHANGED_BANK_DETAILS",
    "CRYPTO_DESTINATION",
    "COACHING_TO_LIE",
    "THREAT_OR_FEAR",
    "TOO_GOOD_TO_BE_TRUE",
    "PAYEE_NAME_MISMATCH",
    "WATCHLIST_MATCH",
]
Severity = Literal["LOW", "MEDIUM", "HIGH"]

# Other enums used across the API and Firestore (API_SPEC, DATA_SPEC)
Language = Literal["en", "zh", "ms", "ta"]  # en + zh in the MVP
DestType = Literal["LOCAL_BANK", "OVERSEAS", "CRYPTO_EXCHANGE", "MERCHANT", "PAYNOW"]
CheckStatus = Literal["SCORING", "CHECKIN", "ANALYSING", "DONE", "ERROR"]
ProgressStage = Literal[
    "SCORING", "ANALYSING_EVIDENCE", "CHECKING_INTEL", "DECIDING", "WRITING", "DONE"
]
ProgressEventType = Literal["status", "partial", "done", "error"]
CustomerChoice = Literal["COOL_OFF", "CALLED_CONTACT", "PROCEEDED", "CANCELLED"]
AnalystAction = Literal["RELEASE", "HOLD", "ESCALATE", "REPORT_SCAM"]
CaseStatus = Literal["OPEN", "RELEASED", "HELD", "ESCALATED", "REPORTED"]
WatchlistType = Literal["PHONE", "URL", "DOMAIN", "ACCOUNT"]
WatchlistSource = Literal["SEED", "ANALYST_REPORT"]
MessageRole = Literal["assistant", "customer"]
UploadContentType = Literal["image/png", "image/jpeg", "image/webp", "application/pdf"]
ErrorCode = Literal["VALIDATION_ERROR", "NOT_FOUND", "FORBIDDEN", "ANALYSIS_TIMEOUT", "INTERNAL"]
TxnReasonCode = Literal[
    "NEW_PAYEE",
    "AMOUNT_SPIKE",
    "CRYPTO_DESTINATION",
    "OVERSEAS_DESTINATION",
    "NEW_PAYEE_VELOCITY",
    "NIGHT_TIME",
    "SENIOR_CUSTOMER",
    "HIGH_BALANCE_SHARE",
    "WATCHLIST_MATCH",
]

ACTION_FOR_VERDICT: dict[Verdict, Action] = {
    "GREEN": "PROCEED",
    "AMBER": "COOL_OFF",
    "RED": "HOLD_FOR_REVIEW",
}


# ---------------------------------------------------------------------------
# Transfer + transaction risk (AGENTS_SPEC §1)
# ---------------------------------------------------------------------------


class Transfer(BaseModel):
    payee_name: str = Field(min_length=1, max_length=120)
    account_number: str = Field(min_length=1, max_length=40)
    bank_name: str | None = Field(default=None, max_length=80)
    dest_type: DestType = "LOCAL_BANK"
    amount: float = Field(gt=0)
    currency: str = "SGD"
    note: str | None = Field(default=None, max_length=140)


class TxnRiskReason(BaseModel):
    code: TxnReasonCode
    label: str
    points: int


class TxnFeatures(BaseModel):
    is_new_payee: bool
    amount_vs_median_90d: float | None = None  # None when there is no 90-day history
    dest_type: DestType
    transfers_to_new_payees_24h: int = 0
    hour_local: int = Field(ge=0, le=23)
    customer_age: int | None = None
    balance_share: float | None = None  # amount / balance
    watchlist_hit: bool = False


class TxnRisk(BaseModel):
    score: int = Field(ge=0, le=100)
    reasons: list[TxnRiskReason] = Field(default_factory=list)
    features: TxnFeatures | None = None


# ---------------------------------------------------------------------------
# Evidence agent output (AGENTS_SPEC §2)
# ---------------------------------------------------------------------------


class RedFlag(BaseModel):
    code: RedFlagCode
    severity: Severity
    quote: str = Field(description="Exact text from the evidence that shows this flag.")
    evidence_index: int | None = Field(
        default=None, description="Index of the evidence part the quote comes from."
    )
    box_2d: list[int] | None = Field(
        default=None,
        description="[ymin, xmin, ymax, xmax] normalised 0-1000 on the referenced image.",
    )

    @field_validator("box_2d")
    @classmethod
    def _drop_invalid_box(cls, v: list[int] | None) -> list[int] | None:
        # An invalid box is dropped (set to None), never a reason to reject the whole analysis.
        if v is None:
            return None
        if len(v) != 4 or any(not 0 <= n <= 1000 for n in v):
            return None
        ymin, xmin, ymax, xmax = v
        if ymin >= ymax or xmin >= xmax:
            return None
        return v


class ClaimedSender(BaseModel):
    name: str | None = None
    claimed_org: str | None = None
    channel: str | None = None


class PaymentInstruction(BaseModel):
    amount: float | None = None
    account: str | None = None
    reason_given: str | None = None


class Entities(BaseModel):
    phones: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    apps: list[str] = Field(default_factory=list)


class EvidenceAnalysis(BaseModel):
    evidence_present: bool
    summary: str
    claimed_sender: ClaimedSender | None = None
    payment_instruction: PaymentInstruction | None = None
    entities: Entities = Field(default_factory=Entities)
    red_flags: list[RedFlag] = Field(default_factory=list, max_length=6)
    typology_guess: Typology = "UNKNOWN"
    typology_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language_detected: str = "en"
    injection_attempt_detected: bool = False


# ---------------------------------------------------------------------------
# Scam-Intel agent output (AGENTS_SPEC §3)
# ---------------------------------------------------------------------------


class WatchlistMatch(BaseModel):
    type: WatchlistType
    value: str
    source: WatchlistSource
    reported_count: int = 1


class WebFinding(BaseModel):
    query: str
    finding: str
    sources: list[str] = Field(default_factory=list)
    risk: Severity = "LOW"


class IntelResult(BaseModel):
    watchlist_matches: list[WatchlistMatch] = Field(default_factory=list)
    web_findings: list[WebFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Fusion policy output (AGENTS_SPEC §4); deterministic, not an LLM
# ---------------------------------------------------------------------------


class FusionResult(BaseModel):
    verdict: Verdict
    action: Action
    reasons: list[str] = Field(default_factory=list)
    top_flags: list[RedFlag] = Field(default_factory=list, max_length=4)
    needs_review: bool = False


# ---------------------------------------------------------------------------
# Customer Explainer output (AGENTS_SPEC §5). Word limits are enforced in
# post-processing, not here, so a long answer is trimmed rather than rejected.
# ---------------------------------------------------------------------------


class FlagExplanation(BaseModel):
    code: RedFlagCode
    text: str


class CustomerMessage(BaseModel):
    language: Language
    headline: str
    body: str
    flag_explanations: list[FlagExplanation] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Case-File agent output (AGENTS_SPEC §6)
# ---------------------------------------------------------------------------


class EvidencePoint(BaseModel):
    flag: RedFlagCode
    quote: str
    evidence_index: int | None = None


class CaseFile(BaseModel):
    title: str
    summary: str
    timeline: list[str] = Field(default_factory=list)
    evidence_points: list[EvidencePoint] = Field(default_factory=list)
    intel_points: list[str] = Field(default_factory=list)
    recommended_action: AnalystAction
    recommended_reason: str
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Customer API (API_SPEC "Customer endpoints")
# ---------------------------------------------------------------------------


class CreateCheckRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=32)
    transfer: Transfer
    language: Language | None = None


class CheckInQuestion(BaseModel):
    text: str
    quick_replies: list[str] = Field(default_factory=list)


class CreateCheckResponse(BaseModel):
    """201 from POST /checks: either a check-in question, or an immediate GREEN."""

    check_id: str
    status: CheckStatus
    txn_risk: TxnRisk | None = None
    question: CheckInQuestion | None = None
    verdict: Verdict | None = None
    customer_message: CustomerMessage | None = None


class SignUploadRequest(BaseModel):
    check_id: str
    filename: str = Field(min_length=1, max_length=200)
    content_type: UploadContentType


class SignUploadResponse(BaseModel):
    upload_url: str
    gcs_uri: str
    expires_in: int


class CheckMessageRequest(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    quick_reply: str | None = Field(default=None, max_length=120)
    evidence_uris: list[str] = Field(default_factory=list, max_length=3)


class LatencyMs(BaseModel):
    txn: int | None = None
    evidence: int | None = None
    intel: int | None = None
    explainer: int | None = None
    casefile: int | None = None
    total: int | None = None


class TokenUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    in_: int = Field(default=0, alias="in")
    out: int = 0


class CheckMessageResponse(BaseModel):
    """200 from POST /checks/{id}/messages. Also the payload of the SSE `done` event."""

    check_id: str
    status: CheckStatus
    verdict: Verdict | None = None
    action: Action | None = None
    needs_review: bool = False
    typology: Typology | None = None
    confidence: float | None = None
    top_flags: list[RedFlag] = Field(default_factory=list)
    customer_message: CustomerMessage | None = None
    case_id: str | None = None
    latency_ms: LatencyMs = Field(default_factory=LatencyMs)
    question: CheckInQuestion | None = None  # only for the one allowed follow-up turn


class ProgressEvent(BaseModel):
    """One SSE event from GET /checks/{id}/events."""

    type: ProgressEventType
    stage: ProgressStage | None = None
    data: dict[str, object] | None = None


class ChatMessage(BaseModel):
    role: MessageRole
    text: str
    evidence_uris: list[str] = Field(default_factory=list)
    ts: datetime


class CheckRecord(BaseModel):
    """`checks/{check_id}` in Firestore; GET /checks/{id} returns it (no case file)."""

    check_id: str
    customer_id: str
    created_at: datetime
    status: CheckStatus
    transfer: Transfer
    language: Language = "en"
    txn_risk: TxnRisk | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    evidence: EvidenceAnalysis | None = None
    intel: IntelResult | None = None
    fusion: FusionResult | None = None
    customer_message: CustomerMessage | None = None
    case_id: str | None = None
    latency_ms: LatencyMs = Field(default_factory=LatencyMs)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    customer_choice: CustomerChoice | None = None


class ChoiceRequest(BaseModel):
    choice: CustomerChoice


class FeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Analyst API (API_SPEC "Analyst endpoints")
# ---------------------------------------------------------------------------


class CaseRecord(BaseModel):
    """`cases/{case_id}` in Firestore (AMBER/RED only)."""

    case_id: str
    check_id: str
    customer_id: str
    customer_name: str
    customer_age: int | None = None
    amount: float
    verdict: Verdict
    typology: Typology
    confidence: float = Field(ge=0.0, le=1.0)
    case_file: CaseFile | None = None
    status: CaseStatus = "OPEN"
    assigned_to: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    decision_note: str | None = None


class CaseSummary(BaseModel):
    """A row in GET /cases (the console mainly uses the Firestore listener)."""

    case_id: str
    check_id: str
    customer_name: str
    customer_age: int | None = None
    amount: float
    verdict: Verdict
    typology: Typology
    confidence: float
    status: CaseStatus
    title: str | None = None
    created_at: datetime


class EvidenceLink(BaseModel):
    index: int
    url: str  # signed read URL, 5 minutes
    content_type: str


class AuditEntry(BaseModel):
    """`audit/{auto_id}`, append-only."""

    actor: str
    action: AnalystAction | str
    case_id: str
    ts: datetime
    note: str | None = None


class CaseDetail(BaseModel):
    """GET /cases/{case_id}."""

    case: CaseRecord
    transfer: Transfer
    txn_risk: TxnRisk | None = None
    evidence: EvidenceAnalysis | None = None
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    intel: IntelResult | None = None
    fusion: FusionResult | None = None
    audit: list[AuditEntry] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    action: AnalystAction
    note: str | None = Field(default=None, max_length=1000)


class DecisionResponse(BaseModel):
    case_id: str
    status: CaseStatus
    watchlist_added: int = 0  # REPORT_SCAM only; drives the "N entities added" toast


class WatchlistEntry(BaseModel):
    """`watchlist/{normalised_value}`."""

    type: WatchlistType
    value: str
    source: WatchlistSource
    reported_count: int = 1
    first_seen: datetime
    last_seen: datetime
    typologies: list[Typology] = Field(default_factory=list)


class FeedbackRecord(BaseModel):
    """`feedback/{auto_id}`."""

    check_id: str
    helpful: bool
    comment: str | None = None
    ts: datetime


class LatencyPercentiles(BaseModel):
    p50: int
    p95: int


class TypologyCount(BaseModel):
    typology: Typology
    count: int


class MetricsResponse(BaseModel):
    """GET /metrics?range=today|7d."""

    checks: int
    verdicts: dict[Verdict, int]
    money_protected_sgd: float
    false_positive_rate: float
    latency_ms: LatencyPercentiles
    top_typologies: list[TypologyCount] = Field(default_factory=list)
    cost_per_check_usd: float | None = None


# ---------------------------------------------------------------------------
# Ops + errors
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    ok: bool
    model: str
    data_backend: str
    dependencies: dict[str, bool] | None = None  # Firestore, BigQuery, model (cached)


class ResetDemoResponse(BaseModel):
    checks_deleted: int
    cases_deleted: int
    watchlist_deleted: int


class SelftestResponse(BaseModel):
    passed: bool
    verdict: Verdict | None = None
    latency_ms: int
    detail: str | None = None


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
