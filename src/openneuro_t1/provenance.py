"""What produced the outputs: package versions, Docker images, timings."""

import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .paths import atomic_output

PIPELINE_NAME = "openneuro-t1-pipeline"
PACKAGES = ("niwrap", "nilearn", "nibabel", "templateflow")


def pipeline_version() -> str:
    """The version declared in pyproject.toml."""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _write_json(path: Path, content: dict[str, Any]) -> None:
    with atomic_output(path) as partial:
        partial.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")


def write_dataset_description(path: Path, s3_uri: str, raw_description: Path) -> None:
    """The BIDS dataset_description.json that makes results/ a derivatives dataset."""
    source: dict[str, str] = {"URL": s3_uri}
    raw = json.loads(raw_description.read_text(encoding="utf-8"))
    if raw.get("DOI"):
        source["DOI"] = raw["DOI"]
    _write_json(
        path,
        {
            "Name": "openneuro-t1-pipeline derivatives",
            "BIDSVersion": "1.10.0",
            "DatasetType": "derivative",
            "GeneratedBy": [{"Name": PIPELINE_NAME, "Version": pipeline_version()}],
            "SourceDatasets": [source],
        },
    )


def inspect_images(tags: list[str]) -> list[dict[str, str]]:
    """Tag, registry digest and image ID of each Docker image, from `docker image inspect`."""
    images = []
    for tag in tags:
        result = subprocess.run(
            ["docker", "image", "inspect", tag],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(result.stdout)[0]
        digests = info.get("RepoDigests") or []
        images.append(
            {
                "tag": tag,
                "digest": digests[0].split("@", 1)[1] if digests else info["Id"],
                "image_id": info["Id"],
            }
        )
    return images


def write_runinfo(
    path: Path,
    subject: str,
    started: datetime,
    finished: datetime,
    steps: dict[str, dict[str, Any]],
    images: list[dict[str, str]],
) -> None:
    _write_json(
        path,
        {
            "subject": subject,
            "started": started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "packages": {name: version(name) for name in PACKAGES},
            "docker_default_platform": os.environ.get("DOCKER_DEFAULT_PLATFORM"),
            "docker_images": images,
            "steps": steps,
        },
    )
