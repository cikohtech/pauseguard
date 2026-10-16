"""Evidence uploads (SECURITY_PRIVACY §2): where the customer's screenshots and PDFs live.

    GcsEvidenceStore    cloud: `gs://EVIDENCE_BUCKET/checks/{check_id}/{name}`, V4 signed URLs
                        (PUT 10 min, GET 5 min). Uniform access, no public objects, 30-day delete.
    LocalEvidenceStore  local dev: `.local_uploads/checks/{check_id}/{name}`, behind the API's
                        own HMAC-signed URLs (PUT/GET /api/v1/uploads/local/...).

Both hand out the same thing, a URL to PUT the bytes to plus the headers to send, so the web
client has one upload path. The returned URI goes into `evidence_uris`; the evidence agent reads
gs:// URIs through Vertex AI and local paths from disk (local dev only).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from app.config import REPO_ROOT, Settings
from app.models.schemas import SignUploadResponse, UploadContentType

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_CHECK = 3
UPLOAD_TTL_SECONDS = 600
READ_TTL_SECONDS = 300
EXT_FOR_TYPE: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
TYPE_FOR_EXT = {ext: ct for ct, ext in EXT_FOR_TYPE.items()} | {".jpeg": "image/jpeg"}
CHECK_ID = re.compile(r"^chk_[0-9A-Z]{26}$")
OBJECT_NAME = re.compile(r"^[0-9]-[A-Za-z0-9._-]{1,64}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def object_name(index: int, filename: str, content_type: UploadContentType) -> str:
    """`2-chat.png`: the upload's position, a safe stem, and the extension of its content type
    (the evidence agent picks the MIME type from the extension, so they must agree)."""
    stem = _UNSAFE.sub("_", Path(filename).stem).strip("._") or "evidence"
    return f"{index}-{stem[:48]}{EXT_FOR_TYPE[content_type]}"


def content_type_of(uri: str) -> str:
    return TYPE_FOR_EXT.get(Path(uri).suffix.lower(), "application/octet-stream")


class EvidenceStore(Protocol):
    backend: str

    def uri_for(self, check_id: str, name: str) -> str: ...

    async def sign_upload(
        self, check_id: str, name: str, content_type: UploadContentType, *, base_url: str
    ) -> SignUploadResponse: ...

    async def read_url(self, uri: str, *, base_url: str) -> str: ...

    async def put(self, check_id: str, name: str, data: bytes, content_type: str) -> str:
        """Server-side write (no signed URL): /admin/selftest's own evidence. Returns the URI."""
        ...


# --- cloud -----------------------------------------------------------------------------------

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GcsEvidenceStore:
    backend = "gcs"

    def __init__(
        self,
        bucket: str,
        project: str,
        client: Any | None = None,
        signing_credentials: Any | None = None,
    ) -> None:
        self.bucket_name, self.project = bucket, project
        self._client = client
        self._signing_creds = signing_credentials

    @property
    def client(self) -> Any:
        if self._client is None:
            from google.cloud import storage  # type: ignore[attr-defined]

            self._client = storage.Client(project=self.project)
        return self._client

    def uri_for(self, check_id: str, name: str) -> str:
        return f"gs://{self.bucket_name}/checks/{check_id}/{name}"

    def _signing_kwargs(self) -> dict[str, Any]:
        """Cloud Run's credentials have no private key: sign through the IAM signBlob API with
        the service account's own token (needs roles/iam.serviceAccountTokenCreator on itself).
        Not the storage client's token: that one is scoped to Cloud Storage and IAM rejects it
        (ACCESS_TOKEN_SCOPE_INSUFFICIENT), so signBlob gets its own cloud-platform credentials."""
        from google.auth import credentials as ga_credentials
        from google.auth.transport.requests import Request

        if isinstance(self.client._credentials, ga_credentials.Signing):
            return {}
        if self._signing_creds is None:
            import google.auth

            self._signing_creds, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        creds: Any = self._signing_creds  # compute_engine / impersonated credentials
        if not creds.valid:
            creds.refresh(Request())
        return {"service_account_email": creds.service_account_email, "access_token": creds.token}

    def _sign(self, blob_name: str, **kw: Any) -> str:
        blob = self.client.bucket(self.bucket_name).blob(blob_name)
        return str(blob.generate_signed_url(version="v4", **kw, **self._signing_kwargs()))

    async def sign_upload(
        self, check_id: str, name: str, content_type: UploadContentType, *, base_url: str
    ) -> SignUploadResponse:
        headers = {
            "Content-Type": content_type,
            "x-goog-content-length-range": f"0,{MAX_UPLOAD_BYTES}",  # GCS enforces the size
        }
        url = await asyncio.to_thread(
            self._sign,
            f"checks/{check_id}/{name}",
            expiration=timedelta(seconds=UPLOAD_TTL_SECONDS),
            method="PUT",
            content_type=content_type,
            headers={"x-goog-content-length-range": headers["x-goog-content-length-range"]},
        )
        return SignUploadResponse(
            upload_url=url,
            gcs_uri=self.uri_for(check_id, name),
            expires_in=UPLOAD_TTL_SECONDS,
            headers=headers,
        )

    async def read_url(self, uri: str, *, base_url: str) -> str:
        prefix = f"gs://{self.bucket_name}/"
        if not uri.startswith(prefix):
            raise ValueError(f"{uri} is not in the evidence bucket")
        return await asyncio.to_thread(
            self._sign,
            uri.removeprefix(prefix),
            expiration=timedelta(seconds=READ_TTL_SECONDS),
            method="GET",
        )

    async def put(self, check_id: str, name: str, data: bytes, content_type: str) -> str:
        blob = self.client.bucket(self.bucket_name).blob(f"checks/{check_id}/{name}")
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)
        return self.uri_for(check_id, name)


# --- local dev -------------------------------------------------------------------------------


class LocalEvidenceStore:
    """Files on disk, with URLs signed like GCS's: HMAC over method, path, content type and
    expiry, with a key that lives only in this process (a restart voids old URLs)."""

    backend = "local"
    route = "api/v1/uploads/local"

    def __init__(self, root: Path, key: bytes | None = None) -> None:
        self.root = root
        self._key = key or secrets.token_bytes(32)

    def uri_for(self, check_id: str, name: str) -> str:
        path = self.root / "checks" / check_id / name
        # Repo-relative when possible: the evidence agent only reads files inside the repo.
        return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)

    def path_for(self, check_id: str, name: str) -> Path:
        if not CHECK_ID.match(check_id) or not OBJECT_NAME.match(name):
            raise ValueError("bad evidence path")
        return self.root / "checks" / check_id / name

    def _sig(self, method: str, check_id: str, name: str, content_type: str, exp: int) -> str:
        msg = f"{method}\n{check_id}/{name}\n{content_type}\n{exp}".encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def _url(self, base_url: str, method: str, check_id: str, name: str, ttl: int) -> str:
        exp = int(time.time()) + ttl
        sig = self._sig(method, check_id, name, content_type_of(name), exp)
        query = urlencode({"exp": exp, "sig": sig})
        return f"{base_url.rstrip('/')}/{self.route}/{check_id}/{name}?{query}"

    def verify(self, method: str, check_id: str, name: str, exp: int, sig: str) -> bool:
        if exp < time.time():
            return False
        want = self._sig(method, check_id, name, content_type_of(name), exp)
        return hmac.compare_digest(want, sig)

    async def sign_upload(
        self, check_id: str, name: str, content_type: UploadContentType, *, base_url: str
    ) -> SignUploadResponse:
        return SignUploadResponse(
            upload_url=self._url(base_url, "PUT", check_id, name, UPLOAD_TTL_SECONDS),
            gcs_uri=self.uri_for(check_id, name),
            expires_in=UPLOAD_TTL_SECONDS,
            headers={"Content-Type": content_type},
        )

    async def read_url(self, uri: str, *, base_url: str) -> str:
        path = Path(uri)
        check_id, name = path.parent.name, path.name
        if self.uri_for(check_id, name) != uri:
            raise ValueError(f"{uri} is not a local upload")
        return self._url(base_url, "GET", check_id, name, READ_TTL_SECONDS)

    def save(self, check_id: str, name: str, data: bytes) -> None:
        path = self.path_for(check_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def put(self, check_id: str, name: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(self.save, check_id, name, data)
        return self.uri_for(check_id, name)


def evidence_store(settings: Settings) -> EvidenceStore:
    if settings.uploads == "gcs":
        return GcsEvidenceStore(settings.evidence_bucket, settings.google_cloud_project)
    return LocalEvidenceStore(settings.local_uploads_dir)
