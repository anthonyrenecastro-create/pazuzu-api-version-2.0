"""Shared provider exceptions."""
from __future__ import annotations


class ProviderNotConfigured(RuntimeError):
    """Raised when a real provider adapter is requested but no credentials
    or endpoint configuration is present. Never silently mocked."""
