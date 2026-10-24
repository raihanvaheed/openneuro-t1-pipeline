"""Load config/config.yaml and resolve the paths in it against the project root."""

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def project_path(relative: str | Path) -> Path:
    """Resolve a path from the config against the project root, not the cwd."""
    return PROJECT_ROOT / relative
