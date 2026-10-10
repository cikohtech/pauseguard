"""Canonical forms for accounts, phones, URLs and domains.

One function per entity type, used everywhere a value is stored or compared: payee lookup
(TransactionRepo), watchlist document IDs (StateRepo) and the watchlist tool (phase 04).
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from app.models.schemas import WatchlistType

_NON_ALNUM = re.compile(r"[^0-9A-Z]")
_NON_DIGIT = re.compile(r"\D")


def normalise_account(value: str) -> str:
    """'123-45678-9' / '123 45678 9' -> '123456789'. Letters (overseas prefixes) are kept."""
    return _NON_ALNUM.sub("", value.upper())


def normalise_phone(value: str, default_country: str = "65") -> str:
    """'+65 8000 0147' / '8000 0147' / '0065-8000-0147' -> '+6580000147' (E.164-ish)."""
    digits = _NON_DIGIT.sub("", value)
    if value.strip().startswith("00"):
        digits = digits[2:]
    elif not value.strip().startswith("+") and len(digits) == 8:
        digits = default_country + digits  # a local Singapore number
    return "+" + digits


def normalise_domain(value: str) -> str:
    """'https://WWW.Example.example/x' / 'example.example.' -> 'example.example'."""
    v = value.strip().lower()
    host = urlsplit(v if "//" in v else "//" + v).hostname or v
    host = host.rstrip(".")
    return host.removeprefix("www.")


def normalise_url(value: str) -> str:
    """Scheme, 'www.', query, fragment and trailing '/' are dropped; host is lower-cased.

    A URL with no path normalises to its bare domain, so it shares the domain's watchlist doc.
    """
    v = value.strip()
    parts = urlsplit(v if "//" in v else "//" + v)
    host = normalise_domain(parts.hostname or "")
    path = parts.path.rstrip("/")
    return host + path


def normalise_watchlist_value(type_: WatchlistType, value: str) -> str:
    match type_:
        case "PHONE":
            return normalise_phone(value)
        case "ACCOUNT":
            return normalise_account(value)
        case "DOMAIN":
            return normalise_domain(value)
        case "URL":
            return normalise_url(value)


def watchlist_doc_id(normalised_value: str) -> str:
    """Firestore IDs cannot contain '/', so a URL path is percent-encoded ('%2F')."""
    return quote(normalised_value, safe="+:@-._~")
