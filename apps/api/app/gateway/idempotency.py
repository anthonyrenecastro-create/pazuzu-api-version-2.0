"""Idempotency keys: store response (hash + body) by key; replay on duplicates.

Apply IdempotentRoute as route_class on routers handling mutating POSTs.
A repeated Idempotency-Key returns the original response without re-executing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class IdempotencyStore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def replay(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._store.get(key)

    async def store(self, key: str, status_code: int, body: bytes) -> None:
        async with self._lock:
            self._store[key] = {
                "status_code": status_code,
                "body": body.decode("utf-8", errors="replace"),
                "body_hash": hashlib.sha256(body).hexdigest(),
                "replayed": True,
            }


idempotency_store = IdempotencyStore()


class IdempotentRoute(APIRoute):
    """APIRoute that honors the Idempotency-Key header on POST/PUT/PATCH."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            key = request.headers.get("Idempotency-Key")
            if key and request.method in ("POST", "PUT", "PATCH"):
                hit = await idempotency_store.replay(key)
                if hit is not None:
                    return JSONResponse(
                        status_code=hit["status_code"],
                        content=json.loads(hit["body"]),
                        headers={"X-Idempotent-Replayed": "true"},
                    )
            response = await original(request)
            if key and request.method in ("POST", "PUT", "PATCH"):
                if 200 <= response.status_code < 300 and "text/event-stream" not in response.headers.get(
                    "content-type", ""
                ):
                    body: bytes
                    if hasattr(response, "body") and response.body:
                        body = response.body  # type: ignore[attr-defined]
                    else:
                        chunks = [c async for c in response.body_iterator]  # type: ignore[attr-defined]
                        body = b"".join(chunks)
                        response = Response(
                            content=body,
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            media_type=response.media_type,
                        )
                    await idempotency_store.store(key, response.status_code, body)
                    response.headers["X-Idempotent-Replayed"] = "false"
            return response

        return handler
