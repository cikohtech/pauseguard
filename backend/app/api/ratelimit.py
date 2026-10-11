"""Rate limits on POST /checks (SECURITY_PRIVACY §3), so the public demo can't run up costs.

Two moving-window limits, both through slowapi's limiter (memory storage, per instance):
RATE_LIMIT_CHECKS per client IP and RATE_LIMIT_CHECKS_PER_CUSTOMER per customer_id (generous:
every judge shares the same three personas). slowapi's decorator binds a limit at import time
and keys on the request alone, so the route calls `hit()` once the body (customer_id) is parsed.
Callers with the admin token (smoke test, benchmark) are not limited.
"""

from __future__ import annotations

from fastapi import Request
from limits import parse
from slowapi import Limiter

from app.api.errors import ApiError
from app.config import Settings


def client_ip(request: Request, *, behind_proxy: bool) -> str:
    """On Cloud Run the peer is Google's front end; it appends the real client address to
    X-Forwarded-For, so the right-most entry is the one a client can't forge."""
    if behind_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


class CheckRateLimiter:
    def __init__(self, settings: Settings, *, enabled: bool = True) -> None:
        self.behind_proxy = settings.is_cloud
        self.per_ip = parse(settings.rate_limit_checks)
        self.per_customer = parse(settings.rate_limit_checks_per_customer)
        self._limiter = Limiter(
            key_func=lambda r: client_ip(r, behind_proxy=self.behind_proxy),
            storage_uri="memory://",
            strategy="moving-window",
            enabled=enabled,
        )

    def hit(self, request: Request, customer_id: str) -> None:
        if not self._limiter.enabled:
            return
        engine = self._limiter.limiter
        keys = [
            (self.per_ip, "ip", client_ip(request, behind_proxy=self.behind_proxy)),
            (self.per_customer, "customer", customer_id),
        ]
        for limit, scope, key in keys:
            if not engine.test(limit, "checks", scope, key):
                raise ApiError(
                    429,
                    "RATE_LIMITED",
                    f"Too many checks ({limit} per {scope}). Please try again later.",
                )
        for limit, scope, key in keys:
            engine.hit(limit, "checks", scope, key)

    def reset(self) -> None:
        self._limiter.reset()
