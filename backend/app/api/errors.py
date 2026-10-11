"""One error envelope for every failure: {"error": {"code", "message", "details?"}} (API_SPEC).

An analysis timeout is never an error for the customer: POST /checks/{id}/messages answers AMBER +
needs_review instead (api/checks.py). Unexpected exceptions become a 500 INTERNAL without
internals in the message; the traceback goes to the (redacted) log.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.orchestrator import CheckStateError, UnknownCustomerError
from app.data.base import NotFoundError
from app.log import get_logger
from app.models.schemas import ErrorBody, ErrorCode, ErrorResponse

log = get_logger(__name__)

CODE_FOR_STATUS: dict[int, ErrorCode] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "VALIDATION_ERROR",
    409: "CONFLICT",
    413: "VALIDATION_ERROR",
    415: "VALIDATION_ERROR",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: ErrorCode,
        message: str,
        details: list[dict[str, object]] | None = None,
    ):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def conflict(message: str) -> ApiError:
    return ApiError(409, "CONFLICT", message)


def envelope(
    status: int, code: ErrorCode, message: str, details: list[dict[str, object]] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(body.model_dump(mode="json", exclude_none=True), status_code=status)


def _field_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    # `input` and `ctx` are left out: they echo the request (PII) and may not be JSON.
    return [
        {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type"))}
        for e in exc.errors()
    ]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return envelope(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = _field_errors(exc)
        first = details[0] if details else {"loc": [], "msg": "invalid request"}
        where = ".".join(str(p) for p in first["loc"] if p != "body")  # type: ignore[attr-defined]
        message = f"{where}: {first['msg']}" if where else str(first["msg"])
        return envelope(422, "VALIDATION_ERROR", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = CODE_FOR_STATUS.get(exc.status_code, "INTERNAL")
        return envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return envelope(404, "NOT_FOUND", f"{exc} not found")

    @app.exception_handler(CheckStateError)
    async def _state(_: Request, exc: CheckStateError) -> JSONResponse:
        return envelope(409, "CONFLICT", str(exc))

    @app.exception_handler(UnknownCustomerError)
    async def _customer(_: Request, exc: UnknownCustomerError) -> JSONResponse:
        return envelope(422, "VALIDATION_ERROR", str(exc))

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, error=type(exc).__name__)
        return envelope(500, "INTERNAL", "Something went wrong on our side. Please try again.")


def error_docs(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` for the error statuses a route can return."""
    text = {
        401: "Missing or invalid Firebase ID token",
        403: "Signed in, but not allowed (analyst role or admin token needed)",
        404: "No such check, case or file",
        409: "The check or case is not in a state that allows this",
        422: "The request failed validation",
        429: "Too many checks from this client or for this customer",
    }
    # 422 always: FastAPI would otherwise document its own validation schema, not ours.
    return {s: {"model": ErrorResponse, "description": text[s]} for s in {*statuses, 422}}
