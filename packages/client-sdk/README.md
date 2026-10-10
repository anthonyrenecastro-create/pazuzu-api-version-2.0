# PAZUZU client SDK

**Status: NOT_IMPLEMENTED.** This package is a placeholder for the planned
typed client SDKs (Python and TypeScript) for PAZUZU-API v2.0.

## Planned scope

- Typed client for all `/v1/*` API endpoints, generated from the shared
  contracts in `../contracts/` (Pydantic v2 models + the TypeScript mirror).
- Request/response validation, auth (JWT), streaming execution traces.
- Retry + backoff policy aligned with the gateway's rate limits.

## Do not build against this yet

The API surface is still under development by the backend agents. Once the
endpoints are stable, this package will be scaffolded with real code and
contract tests.
