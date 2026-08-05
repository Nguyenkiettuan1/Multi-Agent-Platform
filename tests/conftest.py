"""Pytest configuration."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/multiagent",
)
