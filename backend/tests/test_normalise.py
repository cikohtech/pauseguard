import pytest

from app.data.normalise import (
    normalise_account,
    normalise_domain,
    normalise_phone,
    normalise_url,
    normalise_watchlist_value,
    watchlist_doc_id,
)


@pytest.mark.parametrize(
    "raw",
    ["+65 8000 0147", "+6580000147", "8000 0147", "80000147", "0065 8000 0147", "+65-8000-0147"],
)
def test_phone(raw: str) -> None:
    assert normalise_phone(raw) == "+6580000147"


@pytest.mark.parametrize("raw", ["123-45678-9", "123 45678 9", "123456789", " 123.45678.9 "])
def test_account(raw: str) -> None:
    assert normalise_account(raw) == "123456789"


def test_overseas_account_keeps_letters() -> None:
    assert normalise_account("my12 3456 7890") == "MY1234567890"


@pytest.mark.parametrize(
    "raw",
    [
        "mas-gov-verify.example",
        "MAS-Gov-Verify.example.",
        "www.mas-gov-verify.example",
        "https://mas-gov-verify.example/case/1?x=1",
    ],
)
def test_domain(raw: str) -> None:
    assert normalise_domain(raw) == "mas-gov-verify.example"


def test_url() -> None:
    assert normalise_url("HTTPS://www.Parcel-Redelivery-SG.example/pay-fee/?t=9#x") == (
        "parcel-redelivery-sg.example/pay-fee"
    )
    assert (
        normalise_url("parcel-redelivery-sg.example/pay-fee")
        == "parcel-redelivery-sg.example/pay-fee"
    )
    # No path: the URL and its domain share one watchlist document.
    assert normalise_url("https://taskhub-rewards.example/") == normalise_domain(
        "taskhub-rewards.example"
    )


def test_watchlist_doc_ids_are_valid_firestore_ids() -> None:
    for type_, raw in [
        ("PHONE", "+65 8000 0147"),
        ("URL", "https://a.example/b/c"),
        ("DOMAIN", "a.example"),
        ("ACCOUNT", "123-45678-9"),
    ]:
        doc_id = watchlist_doc_id(normalise_watchlist_value(type_, raw))
        assert "/" not in doc_id and doc_id not in (".", "..") and doc_id
    assert watchlist_doc_id("a.example/b") == "a.example%2Fb"
    assert watchlist_doc_id("+6580000147") == "+6580000147"
