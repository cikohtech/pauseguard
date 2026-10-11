"""Evidence uploads (API_SPEC POST /uploads/sign; SECURITY_PRIVACY §2).

The client asks for a signed URL, PUTs the file's bytes there with the returned headers, then
sends the returned URI in `evidence_uris`. In cloud the URL is a GCS V4 signed URL (10 minutes,
size enforced by GCS). Locally it points at this API (`/uploads/local/...`), signed the same way,
and the file lands in `./.local_uploads`, so the web client has a single code path.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from app.api.checks import load_check
from app.api.deps import CustomerDep, Services, ServicesDep
from app.api.errors import ApiError, conflict, error_docs, not_found
from app.models.schemas import SignUploadRequest, SignUploadResponse
from app.tools.evidence_store import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOADS_PER_CHECK,
    LocalEvidenceStore,
    content_type_of,
    object_name,
)

router = APIRouter(prefix="/uploads", tags=["customer"])


@router.post(
    "/sign",
    response_model=SignUploadResponse,
    responses=error_docs(401, 404, 409, 422),
    summary="Get a signed URL to upload one evidence file",
)
async def sign_upload(
    req: SignUploadRequest,
    request: Request,
    services: ServicesDep,
    _: CustomerDep,
) -> SignUploadResponse:
    """PNG, JPEG, WebP or PDF; at most 10 MB and 3 files per check, while the check is waiting
    for its check-in answer. `PUT` the bytes to `upload_url` with exactly `headers`; the URL
    expires after `expires_in` seconds. Files are deleted after 30 days."""
    check = await load_check(services, req.check_id)
    if check.status != "CHECKIN":
        raise conflict(f"Check {req.check_id} is {check.status}; uploads are for the check-in")
    if len(check.uploads) >= MAX_UPLOADS_PER_CHECK:
        raise conflict(f"At most {MAX_UPLOADS_PER_CHECK} files per check")
    name = object_name(len(check.uploads), req.filename, req.content_type)
    signed = await services.store.sign_upload(
        req.check_id, name, req.content_type, base_url=str(request.base_url)
    )
    await services.state.update_check(req.check_id, uploads=[*check.uploads, signed.gcs_uri])
    return signed


def _local_store(services: Services) -> LocalEvidenceStore:
    if not isinstance(services.store, LocalEvidenceStore):
        raise not_found("Local uploads")  # cloud uses GCS signed URLs
    return services.store


@router.put(
    "/local/{check_id}/{name}",
    include_in_schema=False,  # local dev only: the target of a locally signed upload URL
)
async def put_local_upload(
    check_id: str,
    name: str,
    exp: int,
    sig: str,
    request: Request,
    services: ServicesDep,
) -> Response:
    store = _local_store(services)
    if not store.verify("PUT", check_id, name, exp, sig):
        raise ApiError(403, "FORBIDDEN", "Invalid or expired upload URL")
    if request.headers.get("content-type") != content_type_of(name):
        raise ApiError(415, "VALIDATION_ERROR", f"Content-Type must be {content_type_of(name)}")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "VALIDATION_ERROR", "Files are limited to 10 MB")
    await asyncio.to_thread(store.save, check_id, name, bytes(data))
    return Response(status_code=200)


@router.get("/local/{check_id}/{name}", include_in_schema=False)
async def get_local_upload(
    check_id: str,
    name: str,
    exp: int,
    sig: str,
    services: ServicesDep,
) -> FileResponse:
    store = _local_store(services)
    if not store.verify("GET", check_id, name, exp, sig):
        raise ApiError(403, "FORBIDDEN", "Invalid or expired evidence URL")
    path = store.path_for(check_id, name)
    if not path.is_file():
        raise not_found("Evidence file")
    return FileResponse(
        path, media_type=content_type_of(name), headers={"Cache-Control": "private, max-age=300"}
    )
