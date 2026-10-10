"""PAZUZU-API v2.0 FastAPI backend."""
from __future__ import annotations

import os
import sys

# Ensure the pazuzu-v2 root is importable so `stations.*` lazy imports work.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

__version__ = "2.0.0"
