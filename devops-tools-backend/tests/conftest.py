"""Shared pytest fixtures for the portal test suite."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the backend package (`app.*`) is importable regardless of pytest CWD.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
