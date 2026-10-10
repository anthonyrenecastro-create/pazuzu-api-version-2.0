"""Gateway middleware: correlation IDs, request deadlines, audit logging."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..telemetry import audit_registry, requests_total


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reads X-Correlation-ID or generates one; echoes it back on the response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or uuid4().hex
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class DeadlineMiddleware(BaseHTTPMiddleware):
    """Enforces a per-request deadline. Header X-Request-Deadline-Ms overrides
    the default (PAZUZU_REQUEST_TIMEOUT_MS, 30000). Exceeded -> 504."""

    async def dispatch(self, request: Request, call_next) -> Response:
        default_ms = float(__import__("os").environ.get("PAZUZU_REQUEST_TIMEOUT_MS", "30000"))
        try:
            deadline_ms = float(request.headers.get("X-Request-Deadline-Ms", default_ms))
        except ValueError:
            deadline_ms = default_ms
        try:
            return await asyncio.wait_for(call_next(request), timeout=deadline_ms / 1000.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "request deadline exceeded", "deadline_ms": deadline_ms},
            )


class AuditMiddleware(BaseHTTPMiddleware):
    """Structured JSON-lines audit log to stdout + in-memory audit registry."""

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        correlation_id = getattr(request.state, "correlation_id", None) or uuid4().hex
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            status_code = response.status_code if response is not None else 500
            principal = getattr(request.state, "principal_sub", "anonymous")
            tenant = getattr(request.state, "principal_tenant", "unknown")
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
                "principal": principal,
                "tenant": tenant,
            }
            print(json.dumps(entry), file=sys.stdout, flush=True)
            audit_registry.append(entry)
            requests_total.inc(
                {"method": request.method, "path": request.url.path, "status": str(status_code)}
            )
