"""Evidence store (uploads): safe object names, local signed URLs, GCS signing, the event hub and
the REPORT_SCAM entity rules."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.api.cases import reportable_entities
from app.api.events import EventHub
from app.config import REPO_ROOT, Settings
from app.models.schemas import (
    ChatMessage,
    CheckRecord,
    Entities,
    EvidenceAnalysis,
    ProgressEvent,
    Transfer,
)
from app.tools.evidence_store import (
    GcsEvidenceStore,
    LocalEvidenceStore,
    content_type_of,
    evidence_store,
    object_name,
)

CHECK = "chk_01M4M7HWQ27Z8QG272FFR6YFCB"


def test_object_names_are_safe_and_match_the_content_type() -> None:
    assert object_name(0, "WhatsApp Image 2026-10-11 at 9.41.png", "image/png") == (
        "0-WhatsApp_Image_2026-10-11_at_9.41.png"
    )
    assert object_name(1, "../../etc/passwd", "application/pdf") == "1-passwd.pdf"
    assert object_name(2, "....", "image/jpeg") == "2-evidence.jpg"
    assert object_name(0, "chat.exe", "image/webp").endswith(".webp")
    assert len(object_name(0, "x" * 500, "image/png")) <= 2 + 48 + 4
    assert content_type_of("gs://b/checks/c/0-a.JPEG") == "image/jpeg"
    assert content_type_of("a.gif") == "application/octet-stream"


async def test_local_urls_are_signed_per_method_and_expire(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path)
    signed = await store.sign_upload(CHECK, "0-a.png", "image/png", base_url="http://api/")
    assert signed.upload_url.startswith(f"http://api/api/v1/uploads/local/{CHECK}/0-a.png?exp=")
    query = dict(p.split("=") for p in signed.upload_url.split("?")[1].split("&"))
    exp, sig = int(query["exp"]), query["sig"]
    assert store.verify("PUT", CHECK, "0-a.png", exp, sig)
    assert not store.verify("GET", CHECK, "0-a.png", exp, sig)  # an upload URL can't read
    assert not store.verify("PUT", CHECK, "1-a.png", exp, sig)
    assert not store.verify("PUT", CHECK, "0-a.png", int(time.time()) - 1, sig)
    other = LocalEvidenceStore(tmp_path)  # another process: another key
    assert not other.verify("PUT", CHECK, "0-a.png", exp, sig)

    read = await store.read_url(signed.gcs_uri, base_url="http://api")
    q = dict(p.split("=") for p in read.split("?")[1].split("&"))
    assert store.verify("GET", CHECK, "0-a.png", int(q["exp"]), q["sig"])
    with pytest.raises(ValueError):
        await store.read_url("gs://bucket/checks/x/0-a.png", base_url="http://api")


def test_local_paths_are_validated_and_repo_relative() -> None:
    store = LocalEvidenceStore(REPO_ROOT / ".local_uploads")
    assert store.uri_for(CHECK, "0-a.png") == f".local_uploads/checks/{CHECK}/0-a.png"
    for check_id, name in [("../x", "0-a.png"), (CHECK, "../a.png"), (CHECK, "a.png")]:
        with pytest.raises(ValueError):
            store.path_for(check_id, name)


class FakeBlob:
    def __init__(self, name: str, calls: list[dict[str, Any]]):
        self.name, self.calls = name, calls

    def generate_signed_url(self, **kw: Any) -> str:
        self.calls.append({"blob": self.name, **kw})
        return f"https://storage.googleapis.com/b/{self.name}?X-Goog-Signature=x"


class FakeCreds:
    valid = False
    token = "tok"
    service_account_email = "pauseguard-api@p.iam.gserviceaccount.com"

    def refresh(self, _request: Any) -> None:
        self.valid = True


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._credentials = FakeCreds()

    def bucket(self, _name: str) -> Any:
        client = self

        class Bucket:
            def blob(self, name: str) -> FakeBlob:
                return FakeBlob(name, client.calls)

        return Bucket()


class FakeIamCreds(FakeCreds):
    token = "iam-tok"  # cloud-platform scope, unlike the storage client's token


async def test_gcs_signs_through_iam_with_the_size_limit() -> None:
    client = FakeClient()
    store = GcsEvidenceStore(
        "p-pauseguard-evidence", "p", client=client, signing_credentials=FakeIamCreds()
    )
    signed = await store.sign_upload(CHECK, "0-a.png", "image/png", base_url="ignored")
    assert signed.gcs_uri == f"gs://p-pauseguard-evidence/checks/{CHECK}/0-a.png"
    assert signed.headers == {
        "Content-Type": "image/png",
        "x-goog-content-length-range": "0,10485760",
    }
    put = client.calls[0]
    assert put["blob"] == f"checks/{CHECK}/0-a.png" and put["method"] == "PUT"
    assert put["version"] == "v4" and put["expiration"].total_seconds() == 600
    assert put["service_account_email"] == FakeCreds.service_account_email
    # signBlob needs a cloud-platform token; the storage client's own ("tok") is refused on
    # Cloud Run with ACCESS_TOKEN_SCOPE_INSUFFICIENT.
    assert put["access_token"] == "iam-tok" and put["content_type"] == "image/png"

    await store.read_url(signed.gcs_uri, base_url="ignored")
    get = client.calls[1]
    assert get["method"] == "GET" and get["expiration"].total_seconds() == 300
    with pytest.raises(ValueError):
        await store.read_url("gs://other-bucket/x.png", base_url="ignored")


def test_gcs_signing_credentials_default_to_cloud_platform_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scopes_asked: list[list[str]] = []

    def fake_default(scopes: list[str]) -> tuple[FakeIamCreds, str]:
        scopes_asked.append(scopes)
        return FakeIamCreds(), "p"

    monkeypatch.setattr("google.auth.default", fake_default)
    store = GcsEvidenceStore("p-pauseguard-evidence", "p", client=FakeClient())
    assert store._signing_kwargs()["access_token"] == "iam-tok"
    store._signing_kwargs()  # cached: google.auth.default is asked once
    assert scopes_asked == [["https://www.googleapis.com/auth/cloud-platform"]]


def test_store_choice_follows_settings(tmp_path: Path) -> None:
    local = Settings(_env_file=None, local_uploads_dir=tmp_path)  # type: ignore[call-arg]
    assert local.uploads == "local" and isinstance(evidence_store(local), LocalEvidenceStore)
    cloud = Settings(_env_file=None, K_SERVICE="pauseguard-api")  # type: ignore[call-arg]
    assert cloud.uploads == "gcs" and isinstance(evidence_store(cloud), GcsEvidenceStore)
    with pytest.raises(ValueError, match="UPLOAD_BACKEND=local"):
        Settings(_env_file=None, K_SERVICE="x", upload_backend="local")  # type: ignore[call-arg]


async def test_event_hub_replays_history_and_forgets_it_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.events as events_mod

    monkeypatch.setattr(events_mod, "HISTORY_TTL_SECONDS", 0.05)
    hub = EventHub()
    hub.publish("c", ProgressEvent(type="status", stage="DECIDING"))
    with hub.subscribe("c") as (history, queue):
        assert [e.stage for e in history] == ["DECIDING"]
        hub.publish("c", ProgressEvent(type="done", stage="DONE"))
        assert (await queue.get()).type == "done"
    assert "c" not in hub._subs
    await asyncio.sleep(0.1)
    with hub.subscribe("c") as (history, _):
        assert history == []


# --- REPORT_SCAM entity rules ---------------------------------------------------------------


def checked(entities: dict[str, list[str]], pasted: str | None = None) -> CheckRecord:
    now = datetime.now(UTC)
    return CheckRecord(
        check_id=CHECK,
        customer_id="cust_001",
        created_at=now,
        status="DONE",
        transfer=Transfer(payee_name="P", account_number="123-45678-9", amount=1),
        messages=[
            ChatMessage(role="customer", text="my son +65 8000 0301", pasted_text=pasted, ts=now)
        ],
        evidence=EvidenceAnalysis(
            evidence_present=True, summary="s", entities=Entities.model_validate(entities)
        ),
    )


def test_reportable_entities() -> None:
    got = reportable_entities(
        checked(
            {
                "phones": ["+65 8000 0147", "8000 0147"],  # the same number twice
                "urls": [
                    "https://www.MAS-gov-verify.example/case/2231?x=1",
                    "mas-gov-verify.example",
                    "https://www.mas.gov.sg/contact",  # the real regulator: never
                    "https://t.me/joinchat/abc",  # a shared platform: this link only
                    "https://wa.me",  # a bare shared host: nothing
                ],
                "accounts": ["123 45678 9"],
            },
            pasted="Pay to 556-208417-390 now",
        )
    )
    assert got == [
        ("PHONE", "+6580000147"),
        ("ACCOUNT", "556208417390"),
        ("ACCOUNT", "123456789"),
        ("DOMAIN", "mas-gov-verify.example"),
        ("URL", "t.me/joinchat/abc"),
    ]  # the customer's own answer (their son's number) is not evidence


def test_no_evidence_still_reports_the_payee_account() -> None:
    c = checked({}).model_copy(update={"evidence": None})
    assert reportable_entities(c) == [("ACCOUNT", "123456789")]
