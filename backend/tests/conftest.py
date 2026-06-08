"""Shared test configuration.

Forces mock-LLM mode and an isolated SQLite data dir *before* any app module
imports (so the cached Settings pick them up), and wipes that dir once per
session for deterministic cross-run / meta assertions.
"""
from __future__ import annotations

import os
import shutil

os.environ.setdefault("VOLC_MOCK", "1")
os.environ.setdefault("DATA_DIR", "./.test-data")

# Clean the test data dir once at collection time.
shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
