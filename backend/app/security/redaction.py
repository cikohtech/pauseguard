"""PII masking for logs (SECURITY_PRIVACY §2).

Masks phone numbers, account numbers, NRIC-like IDs, emails and ID tokens in log lines. It is not
applied to the analyst case file, where those values are the evidence. `redact_processor` plugs into
structlog, so every JSON log line is masked before it is written.
"""

from __future__ import annotations

import re
from typing import Any

from structlog.typing import EventDict, WrappedLogger

# Order matters: emails, NRICs and IBAN-like accounts first (they contain digit runs that look
# like phones), then phones, then the broad account pattern.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Firebase ID tokens (JWTs), e.g. the SSE route's ?access_token= in an access-log line.
    ("[TOKEN]", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")),
    ("[EMAIL]", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("[NRIC]", re.compile(r"(?<![A-Za-z0-9])[STFGMstfgm]\d{7}[A-Za-z](?![A-Za-z0-9])")),
    # IBAN-like overseas accounts (MY47 8820 1365).
    ("[ACCOUNT]", re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[\s-]?[0-9A-Z]{4}){2,7}(?![\w])")),
    # International (+65 8000 0147, 0065-8000-0147, +60 12-345 6789).
    (
        "[PHONE]",
        re.compile(r"(?<![\w+])(?:\+|00)\d{1,3}[\s-]?\d{1,4}(?:[\s-]?\d{2,4}){1,3}(?![\w])"),
    ),
    # Singapore local (8000 0147, 91234567): 8 digits starting with 3, 6, 8 or 9.
    ("[PHONE]", re.compile(r"(?<![\w-])(?<!\d\.)[3689]\d{3}[\s-]?\d{4}(?![\w-]|\.\d)")),
    # Accounts: 9-18 digits, optionally grouped with dashes or spaces (123-45678-9).
    ("[ACCOUNT]", re.compile(r"(?<![\w.])\d(?:[\s-]?\d){8,17}(?![\w.])")),
]

# Log fields that never hold PII and must stay exact.
_SKIP_KEYS = frozenset({"timestamp", "severity", "logger", "level"})


def redact(text: str) -> str:
    for label, rx in _RULES:
        text = rx.sub(label, text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact_value(v) for v in value)
    return value


def redact_processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: mask PII in every string value of the event."""
    return {k: v if k in _SKIP_KEYS else redact_value(v) for k, v in event_dict.items()}
