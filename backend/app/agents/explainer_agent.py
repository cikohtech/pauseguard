"""Customer Explainer agent (AGENTS_SPEC §5): the message on the customer's AMBER/RED screen.

    run = await explainer.explain(ExplainRequest(fusion=..., language="zh", ...))
    run.message    CustomerMessage, always valid (a static template if the model failed)

The model writes the headline and body in the customer's language. The explanation next to each
numbered box and the next steps (pause, call the trusted contact, call 1799) come from reviewed
en/zh templates, which keeps the call short and puts no model-written text beside the boxes.
GREEN uses `green_message()` (no LLM call). An AMBER that only exists because the analysis failed
has nothing to explain, so it uses a static "we'll review it" message too. Post-processing is
deterministic: word limits are enforced by trimming (en: words, zh: characters), links are
removed, and an AMBER message may not call the payment a scam as a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.genai import types

from app.agents._runtime import (
    AgentRunner,
    count_tokens,
    generate_config,
    load_prompt,
    neutralise,
    parse_json_object,
    resolve_model,
)
from app.config import Settings, get_settings
from app.log import get_logger
from app.models.schemas import (
    CustomerMessage,
    CustomerMessageDraft,
    FlagExplanation,
    FusionResult,
    Language,
    RedFlagCode,
    TokenUsage,
    Typology,
    Verdict,
)

log = get_logger(__name__)

AGENT_NAME = "explainer_agent"
MVP_LANGUAGES: tuple[Language, ...] = ("en", "zh")
# (headline, body) limits: words for English, characters for Chinese. The reviewed flag texts
# keep to 20 words / 40 characters (AGENTS_SPEC §5; checked by a test).
LIMITS = {"en": (8, 60), "zh": (16, 120)}
FLAG_TEXT_LIMIT = {"en": 20, "zh": 40}

TYPOLOGY_LABELS: dict[Typology, tuple[str, str]] = {
    "GOV_OFFICIAL_IMPERSONATION": ("government official impersonation", "冒充政府官员"),
    "INVESTMENT": ("investment scam", "投资诈骗"),
    "JOB_TASK": ("job or task scam", "求职刷单诈骗"),
    "PHISHING": ("phishing", "钓鱼诈骗"),
    "ECOMMERCE": ("online shopping scam", "网购诈骗"),
    "ROMANCE": ("romance scam", "感情诈骗"),
    "FAKE_FRIEND": ("fake friend scam", "冒充朋友诈骗"),
    "BEC_INVOICE": ("fake invoice / changed bank details", "假发票或更改收款账户"),
    "NONE": ("no scam pattern", "没有诈骗特征"),
    "UNKNOWN": ("unclear", "不确定"),
}

FLAG_TEXT: dict[RedFlagCode, tuple[str, str]] = {
    "AUTHORITY_CLAIM": (
        "Someone claims to be an official. Real officers never ask you to transfer money.",
        "对方自称是官员。真正的官员绝不会要求您转账。",
    ),
    "URGENCY": (
        "They rush you. Scammers create pressure so you don't stop to check.",
        "对方催您快点做。骗子制造压力，让您没时间核实。",
    ),
    "SECRECY_REQUEST": (
        "They ask you to keep it secret. Real organisations never ask you to hide things.",
        "对方要您保密。正规机构绝不会叫您瞒着银行或家人。",
    ),
    "SAFE_ACCOUNT": (
        "There is no such thing as a 'safe account'. Officials never ask you to move money.",
        "根本没有“安全账户”。官员绝不会要求您转移存款。",
    ),
    "GUARANTEED_RETURNS": (
        "Guaranteed high returns are a warning sign. Real investments always carry risk.",
        "保证高回报是危险信号。真正的投资都有风险。",
    ),
    "UPFRONT_FEE": (
        "You are asked to pay a fee first. This is a common trick to take your money.",
        "要您先付费用，这是常见的骗钱手法。",
    ),
    "PAY_TO_EARN": (
        "Real jobs never ask you to pay money to earn money.",
        "正规工作绝不会要您先付钱才能赚钱。",
    ),
    "OFF_PLATFORM_PAYMENT": (
        "They want you to pay a personal account instead of the normal, protected way.",
        "对方要您绕过正规渠道，转到个人账户。",
    ),
    "REMOTE_ACCESS_APP": (
        "Never install an app that lets a stranger control your phone. Banks never ask this.",
        "不要安装让陌生人控制手机的应用。银行绝不会这样要求。",
    ),
    "SUSPICIOUS_URL": (
        "The link does not belong to the real organisation. It may steal your details.",
        "这个链接不属于真正的机构，可能会盗取您的资料。",
    ),
    "NEW_NUMBER_FRIEND": (
        "A 'friend' on a new number asking for money is a known trick. Call their old number.",
        "用新号码借钱的“朋友”是常见骗局。请先打旧号码确认。",
    ),
    "CHANGED_BANK_DETAILS": (
        "Bank details that suddenly change are a warning sign. Check with a number you know.",
        "收款账户突然更改是危险信号。请用您已知的号码确认。",
    ),
    "CRYPTO_DESTINATION": (
        "Money sent to crypto is very hard to get back.",
        "转到加密货币的钱很难追回。",
    ),
    "COACHING_TO_LIE": (
        "They told you what to say to the bank. Honest people never ask you to lie.",
        "对方教您怎么跟银行说。诚实的人不会叫您对银行说谎。",
    ),
    "THREAT_OR_FEAR": (
        "They threaten you so you act fast. Real authorities don't threaten arrest by chat.",
        "对方用威胁逼您快点行动。真正的执法人员不会在聊天里威胁逮捕。",
    ),
    "TOO_GOOD_TO_BE_TRUE": (
        "The offer sounds too good to be true. That is how scammers hook people.",
        "好得难以置信的条件，正是骗子的诱饵。",
    ),
    "PAYEE_NAME_MISMATCH": (
        "The account name does not match who you think you are paying.",
        "收款人姓名和您以为要付的人不一致。",
    ),
    "WATCHLIST_MATCH": (
        "Other customers have reported this number or account to us as a scam.",
        "其他客户已向我们举报这个号码或账户涉及诈骗。",
    ),
}

# Static messages: (headline, body) per language.
GREEN = {
    "en": ("Looks good", "Your transfer is on its way."),
    "zh": ("一切正常", "您的转账正在处理中。"),
}
AMBER = {
    "en": (
        "Let's pause and check this payment",
        "This looks like a known scam. This is not your fault. Scammers are very convincing. "
        "We suggest pausing for 24 hours and talking to someone you trust before you send money.",
    ),
    "zh": (
        "我们先暂停核实一下",
        "这看起来像常见的骗局。这不是您的错，骗子非常善于骗人。"
        "建议您先暂停24小时，和信任的人商量后再决定是否转账。",
    ),
}
REVIEW = {
    "en": (
        "Let's take a moment before sending",
        "We couldn't finish checking this payment, so a member of our team will review it. "
        "Please pause for now and talk to someone you trust before you send money.",
    ),
    "zh": (
        "转账前请先稍等",
        "我们还没有完成这笔转账的检查，团队成员会进行复核。请先暂停，并和信任的人商量后再转账。",
    ),
}
RED = {
    "en": (
        "We've paused this transfer to protect you",
        "This payment shows clear signs of a scam. This is not your fault. Scammers are very "
        "convincing. Our fraud team will call you within 30 minutes on your registered number. "
        "Never share your OTP with anyone.",
    ),
    "zh": (
        "为保护您，我们已暂停这笔转账",
        "这笔转账有明显的诈骗迹象。这不是您的错，骗子非常善于骗人。"
        "我们的反诈骗团队会在30分钟内拨打您登记的号码联系您。请勿向任何人透露验证码。",
    ),
}
HELPLINE_STEP = {"en": "Call the 1799 anti-scam helpline", "zh": "拨打1799反诈骗热线"}
SOMEONE = {"en": "someone you trust", "zh": "您信任的人"}

_LINK = re.compile(
    r"https?://\S+|www\.\S+|\b(?:[a-z0-9-]+\.)+(?:com|net|org|sg|gov|io|app|xyz|example)\b\S*",
    re.I,
)
_CERTAIN_SCAM = re.compile(
    r"\b(?:you\s+are|you're)\s+being\s+scammed\b|\bthis\s+is\s+(?:definitely\s+|certainly\s+)?"
    r"(?:a\s+scam|fraud)\b|您被骗了|您正在被骗|这是诈骗|这就是诈骗|肯定是诈骗|一定是诈骗",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.!?。！？])\s*")


def lang_of(language: Language) -> Language:
    """ms and ta are stretch goals: until then those customers get English."""
    return language if language in MVP_LANGUAGES else "en"


def age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age >= 60:
        return "60+"
    if age >= 45:
        return "45-59"
    return "30-44" if age >= 30 else "18-29"


def green_message(language: Language) -> CustomerMessage:
    lang = lang_of(language)
    headline, body = GREEN[lang]
    return CustomerMessage(language=lang, headline=headline, body=body)


def _size(text: str, lang: str) -> int:
    return len(text.split()) if lang == "en" else len(re.sub(r"\s", "", text))


def limit(text: str, max_units: int, lang: str) -> str:
    """Trim to the limit: whole sentences when possible, else a hard cut with '…'."""
    text = " ".join(text.split()) if lang == "en" else text.strip()
    if _size(text, lang) <= max_units:
        return text
    kept = ""
    for sentence in (s for s in _SENTENCE.split(text) if s):
        candidate = f"{kept} {sentence}".strip() if lang == "en" else kept + sentence
        if _size(candidate, lang) > max_units:
            break
        kept = candidate
    if kept:
        return kept
    if lang == "en":
        return " ".join(text.split()[:max_units]).rstrip(",;:") + "…"
    return text[: max_units - 1] + "…"


def _clean(text: str) -> str:
    return " ".join(_LINK.sub("", text).split()) if text else text


def _contact(name: str | None, lang: Language) -> str:
    return name or SOMEONE[lang]


def static_message(
    verdict: Verdict,
    language: Language,
    fusion: FusionResult,
    *,
    trusted_contact: str | None = None,
) -> CustomerMessage:
    """The template for a verdict (the fallback when the model fails, and the review message)."""
    lang = lang_of(language)
    if verdict == "GREEN":
        return green_message(lang)
    if verdict == "RED":
        (headline, body), first = RED[lang], ("Wait for our call", "等待我们的来电")
    else:
        texts = REVIEW if fusion.needs_review and not fusion.top_flags else AMBER
        (headline, body), first = texts[lang], ("Pause for 24 hours", "暂停24小时")
    i = MVP_LANGUAGES.index(lang)
    contact = _contact(trusted_contact, lang)
    call = f"Call {contact}" if lang == "en" else f"打电话给{contact}"
    return CustomerMessage(
        language=lang,
        headline=headline,
        body=body,
        flag_explanations=[
            FlagExplanation(code=f.code, text=FLAG_TEXT[f.code][i]) for f in fusion.top_flags
        ],
        next_steps=[first[i], call, HELPLINE_STEP[lang]],
    )


def postprocess(
    draft: CustomerMessageDraft,
    verdict: Verdict,
    language: Language,
    fusion: FusionResult,
    *,
    trusted_contact: str | None = None,
) -> CustomerMessage:
    """The model's headline and body, checked and trimmed, plus the reviewed flag explanations
    (one per top flag, in the order of the numbered boxes) and next steps from the template."""
    lang = lang_of(language)
    template = static_message(verdict, lang, fusion, trusted_contact=trusted_contact)
    h_max, b_max = LIMITS[lang]
    headline, body = _clean(draft.headline), _clean(draft.body)
    if verdict == "AMBER" and _CERTAIN_SCAM.search(headline):
        headline = template.headline
    if verdict == "AMBER" and _CERTAIN_SCAM.search(body):
        body = template.body
    return template.model_copy(
        update={
            "headline": limit(headline or template.headline, h_max, lang),
            "body": limit(body or template.body, b_max, lang),
        }
    )


@dataclass
class ExplainRequest:
    fusion: FusionResult
    language: Language = "en"
    typology: Typology = "UNKNOWN"
    age: int | None = None
    trusted_contact: str | None = None
    check_id: str | None = None


@dataclass
class ExplainRun:
    message: CustomerMessage
    called_model: bool
    failed: bool
    latency_ms: int
    tokens: TokenUsage
    error: str | None = None


def build_input(req: ExplainRequest) -> str:
    lang = lang_of(req.language)
    f = req.fusion
    language = "en (English)" if lang == "en" else "zh (write only in Simplified Chinese)"
    label = TYPOLOGY_LABELS[req.typology][0]
    lines = [
        "<verdict>",
        f"Verdict: {f.verdict}",
        f"Language: {language}",
        f"Age band: {age_band(req.age)}",
        f"Trusted contact: {neutralise(_contact(req.trusted_contact, 'en'))}",
        "</verdict>",
        f"Likely scam type: {req.typology} ({label})",
        "Bank's reasons:",
        *(f"- {neutralise(r)}" for r in f.reasons),
        "<flags>",
        *(
            f'{n}. {flag.code}: "{neutralise(flag.quote)}"'
            for n, flag in enumerate(f.top_flags, start=1)
        ),
        "</flags>",
    ]
    return "\n".join(lines)


def build_agent(model: str | BaseLlm | None = None, settings: Settings | None = None) -> LlmAgent:
    settings = settings or get_settings()
    return LlmAgent(
        name=AGENT_NAME,
        description="Writes the calm, plain-language message the customer sees on AMBER or RED.",
        model=resolve_model(model, settings),
        static_instruction=load_prompt("explainer"),
        output_schema=CustomerMessageDraft,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=generate_config(settings),
        after_model_callback=count_tokens,
    )


def _parse(text: str) -> CustomerMessageDraft:
    return CustomerMessageDraft.model_validate(parse_json_object(text))


class ExplainerAgent:
    def __init__(self, model: str | BaseLlm | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.export_sdk_env()
        self.agent = build_agent(model, self.settings)
        self._runner = AgentRunner(self.agent)

    async def explain(self, req: ExplainRequest) -> ExplainRun:
        f = req.fusion
        static = static_message(f.verdict, req.language, f, trusted_contact=req.trusted_contact)
        if f.verdict == "GREEN" or (f.needs_review and not f.top_flags):
            return ExplainRun(static, False, False, 0, TokenUsage())

        parts = [types.Part.from_text(text=build_input(req))]
        run = await self._runner.run(parts, _parse, check_id=req.check_id)
        message = (
            postprocess(run.output, f.verdict, req.language, f, trusted_contact=req.trusted_contact)
            if run.output
            else static
        )
        log.info(
            "customer_message_written",
            check_id=req.check_id,
            agent=AGENT_NAME,
            latency_ms=run.latency_ms,
            tokens_in=run.tokens.in_,
            tokens_out=run.tokens.out,
            attempts=run.attempts,
            failed=run.failed,
            language=message.language,
        )
        return ExplainRun(message, True, run.failed, run.latency_ms, run.tokens, run.error)
