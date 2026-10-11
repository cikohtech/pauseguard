"""What every route needs: the services (built once, lazily) and who is calling.

Auth (SECURITY_PRIVACY §3, prototype level):
- Customers sign in with Firebase anonymous auth; any valid ID token may use the customer routes.
  `customer_id` comes from the persona picker and is checked against the bank's customers.
- Analysts sign in with Firebase email/password; `/cases*` and `/metrics` need the custom claim
  `role=analyst`.
- `X-Admin-Token` (Secret Manager `admin-reset-token`) is for ops and service callers: the admin
  routes, the smoke test and the benchmark. It passes every check and skips the rate limit.
- `AUTH_DISABLED=true` (local dev only; Settings refuses it on Cloud Run) lets every request in as
  a local analyst.
EventSource can't send headers, so the SSE route also accepts `?access_token=` (log lines mask
tokens).
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.agents.orchestrator import Orchestrator
from app.api.errors import ApiError
from app.api.events import EventHub
from app.api.ratelimit import CheckRateLimiter
from app.config import EMULATOR_PROJECT, Settings
from app.data.base import AnalyticsRepo, StateRepo, TransactionRepo
from app.log import get_logger
from app.tools.evidence_store import EvidenceStore

log = get_logger(__name__)

TokenVerifier = Callable[[str], dict[str, Any]]
SHUTDOWN_GRACE_SECONDS = 8.0  # Cloud Run gives 10 s after SIGTERM


@dataclass
class Services:
    settings: Settings
    state: StateRepo
    txn_repo: TransactionRepo
    analytics: AnalyticsRepo
    orchestrator: Orchestrator
    store: EvidenceStore
    verify_token: TokenVerifier
    hub: EventHub = field(default_factory=EventHub)
    limiter: CheckRateLimiter | None = None
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    inflight: set[str] = field(default_factory=set)  # check IDs being analysed here

    def __post_init__(self) -> None:
        if self.limiter is None:
            self.limiter = CheckRateLimiter(self.settings)

    def spawn(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        """A background task that outlives the request (the case file, analytics rows). Kept
        referenced until it finishes, and awaited at shutdown."""
        task = asyncio.create_task(coro, name=name)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def drain(self, grace: float = SHUTDOWN_GRACE_SECONDS) -> None:
        if self.tasks:
            log.info("draining_background_tasks", count=len(self.tasks))
            await asyncio.wait(list(self.tasks), timeout=grace)


def firebase_verifier(settings: Settings) -> TokenVerifier:
    """firebase-admin's ID-token check (Google's public keys, cached by the library). With
    FIREBASE_AUTH_EMULATOR_HOST set it accepts the Auth emulator's unsigned tokens."""
    import firebase_admin
    from firebase_admin import auth

    emulator = bool(settings.firebase_auth_emulator_host) and not settings.is_cloud
    project = EMULATOR_PROJECT if emulator else settings.google_cloud_project
    try:
        app = firebase_admin.get_app("pauseguard")
    except ValueError:
        app = firebase_admin.initialize_app(options={"projectId": project}, name="pauseguard")

    def verify(token: str) -> dict[str, Any]:
        return dict(auth.verify_id_token(token, app=app))

    return verify


def build_services(settings: Settings) -> Services:
    from app.data import get_analytics_repo, get_state_repo, get_transaction_repo
    from app.tools.evidence_store import evidence_store

    txn_repo, state = get_transaction_repo(settings), get_state_repo(settings)
    return Services(
        settings=settings,
        state=state,
        txn_repo=txn_repo,
        analytics=get_analytics_repo(settings),
        orchestrator=Orchestrator(txn_repo=txn_repo, state=state, settings=settings),
        store=evidence_store(settings),
        verify_token=firebase_verifier(settings),
    )


def get_services(request: Request) -> Services:
    """Built on first use, not at import: importing app.main never opens a cloud client."""
    app_state = request.app.state
    if getattr(app_state, "services", None) is None:
        app_state.services = build_services(app_state.settings)
    services: Services = app_state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


# --- who is calling ------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    uid: str
    email: str | None = None
    role: str | None = None  # "analyst" (custom claim), "service" (admin token), or None
    anonymous: bool = False

    @property
    def actor(self) -> str:
        return self.email or self.uid

    @property
    def is_service(self) -> bool:
        return self.role == "service"


LOCAL_ANALYST = Principal(uid="local-dev", email="analyst@harbourbank.example", role="analyst")
SERVICE = Principal(uid="service", role="service")

_bearer = HTTPBearer(auto_error=False, description="Firebase ID token")
_admin_header = APIKeyHeader(
    name="X-Admin-Token", auto_error=False, description="Ops/service token (Secret Manager)"
)


def admin_token_ok(settings: Settings, token: str | None) -> bool:
    expected = settings.admin_reset_token
    return bool(expected and token) and secrets.compare_digest(str(token), str(expected))


BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
AdminTokenDep = Annotated[str | None, Depends(_admin_header)]


async def current_principal(
    request: Request, bearer: BearerDep, admin_token: AdminTokenDep, services: ServicesDep
) -> Principal:
    settings = services.settings
    if admin_token is not None:
        if not admin_token_ok(settings, admin_token):
            raise ApiError(403, "FORBIDDEN", "Invalid admin token")
        return SERVICE
    if settings.auth_disabled:
        return LOCAL_ANALYST
    token = bearer.credentials if bearer else request.query_params.get("access_token")
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "Sign in first (Authorization: Bearer <ID token>)")
    try:
        claims = await asyncio.to_thread(services.verify_token, token)
    except Exception as e:
        log.info("id_token_rejected", error=type(e).__name__)
        raise ApiError(401, "UNAUTHORIZED", "Invalid or expired ID token") from e
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    return Principal(
        uid=str(claims.get("uid") or claims.get("sub")),
        email=claims.get("email"),
        role=claims.get("role"),
        anonymous=provider == "anonymous",
    )


async def require_customer(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    """Any signed-in user (anonymous included)."""
    return principal


async def require_analyst(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    if principal.role not in ("analyst", "service"):
        raise ApiError(403, "FORBIDDEN", "Analyst access only (custom claim role=analyst)")
    return principal


async def require_admin(admin_token: AdminTokenDep, services: ServicesDep) -> Principal:
    if not admin_token_ok(services.settings, admin_token):
        raise ApiError(403, "FORBIDDEN", "Admin token required (X-Admin-Token)")
    return SERVICE


CustomerDep = Annotated[Principal, Depends(require_customer)]
AnalystDep = Annotated[Principal, Depends(require_analyst)]
AdminDep = Annotated[Principal, Depends(require_admin)]
