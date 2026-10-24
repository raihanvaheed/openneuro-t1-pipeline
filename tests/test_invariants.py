"""Permanent project rules from CLAUDE.md. Never weaken these checks."""

import re
import subprocess
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

NEVER_TRACKED = ("local/", "resources/", "results/", "logs/", ".snakemake/")
# Written so that this file does not contain the strings it searches for.
AWS_ACCESS_KEY = re.compile(r"AKIA" + r"[0-9A-Z]{16}")
AWS_SECRET_KEY_NAME = "aws_secret_" + "access_key"


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def test_gitignore_lists_the_folders_that_hold_data_and_local_files():
    lines = (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    for entry in NEVER_TRACKED:
        assert entry in lines, f"{entry} is missing from .gitignore"


def test_no_imaging_data_is_tracked():
    offenders = [f for f in tracked_files() if f.endswith((".nii", ".nii.gz"))]
    assert offenders == []


def test_nothing_from_the_gitignored_folders_is_tracked():
    offenders = [f for f in tracked_files() if f.startswith(NEVER_TRACKED)]
    assert offenders == []


def test_no_tracked_file_holds_an_aws_credential():
    offenders = []
    for name in tracked_files():
        path = PROJECT_ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if AWS_ACCESS_KEY.search(text) or AWS_SECRET_KEY_NAME in text:
            offenders.append(name)
    assert offenders == []


def test_niwrap_is_pinned_to_1_1_0():
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as handle:
        dependencies = tomllib.load(handle)["project"]["dependencies"]
    assert "niwrap==1.1.0" in dependencies
