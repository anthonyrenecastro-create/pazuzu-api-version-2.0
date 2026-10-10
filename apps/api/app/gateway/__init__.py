"""Gateway: auth, rate limiting, middleware, idempotency."""
from .auth import Principal, get_principal, require_admin, require_scopes
from .idempotency import IdempotentRoute, idempotency_store
from .middleware import AuditMiddleware, CorrelationIdMiddleware, DeadlineMiddleware
from .rate_limit import RateLimiter, rate_limit_dep

__all__ = [
    "Principal",
    "get_principal",
    "require_admin",
    "require_scopes",
    "IdempotentRoute",
    "idempotency_store",
    "AuditMiddleware",
    "CorrelationIdMiddleware",
    "DeadlineMiddleware",
    "RateLimiter",
    "rate_limit_dep",
]
