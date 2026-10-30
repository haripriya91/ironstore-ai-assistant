"""Deployment entry point for the IronStore FastAPI application."""

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent / "backend"

# Existing backend modules use imports such as "from app.config import ...".
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402, F401