from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "robots.yaml"
LIBRARY_ROOT_DIR = ROOT_DIR / "storage"
LIBRARY_PROGRAMS_DIR = LIBRARY_ROOT_DIR / "programs"
