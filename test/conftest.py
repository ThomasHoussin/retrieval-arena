"""Shared pytest fixtures and sys.path setup for search_bench tests."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `tools.*` imports resolve
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
