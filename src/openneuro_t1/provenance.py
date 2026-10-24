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
from .paths import FRAGMENT_STEPS, atomic_output

PIPELINE_NAME = "openneuro-t1-pipeline"
PACKAGES = ("niwrap", "nilearn", "nibabel", "templateflow", "snakemake")

# Fields every fragment of a subject must agree on; versions are pinned.
SHARED_FIELDS = ("python", "packages", "docker_default_platform")


class ProvenanceError(RuntimeError):
    """The fragments cannot be merged into one record."""


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


def write_fragment(
    path: Path,
    subject: str,
    step: str,
    started: datetime,
    finished: datetime,
    seconds: float,
    images: list[dict[str, str]],
) -> None:
    """One subject step's record. Images are empty for steps that use no Docker."""
    _write_json(
        path,
        {
            "subject": subject,
            "step": step,
            "started": started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "seconds": seconds,
            "python": sys.version.split()[0],
            "packages": {name: version(name) for name in PACKAGES},
            "docker_default_platform": os.environ.get("DOCKER_DEFAULT_PLATFORM"),
            "docker_images": images,
        },
    )


def merge_fragments(
    subject: str, fragments: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Combine a subject's fragments, keyed by step, into one record."""
    problems = []
    for key in SHARED_FIELDS:
        by_value: dict[str, list[str]] = {}
        for step, fragment in fragments.items():
            by_value.setdefault(json.dumps(fragment[key], sort_keys=True), []).append(
                step
            )
        if len(by_value) > 1:
            groups = "; ".join(
                f"{value} in {', '.join(steps)}" for value, steps in by_value.items()
            )
            problems.append(f"{key} ({groups})")
    if problems:
        raise ProvenanceError(
            f"Fragments for sub-{subject} disagree on " + " and ".join(problems)
        )

    ordered = {step: fragments[step] for step in FRAGMENT_STEPS if step in fragments}
    first = next(iter(ordered.values()))
    images: dict[str, dict[str, str]] = {}
    for fragment in ordered.values():
        for image in fragment["docker_images"]:
            images.setdefault(image["digest"], image)
    return {
        "subject": subject,
        "started": min(f["started"] for f in ordered.values()),
        "finished": max(f["finished"] for f in ordered.values()),
        "python": first["python"],
        "packages": first["packages"],
        "docker_default_platform": first["docker_default_platform"],
        "docker_images": list(images.values()),
        "steps": {
            step: {key: f[key] for key in ("started", "finished", "seconds")}
            for step, f in ordered.items()
        },
    }


def read_fragments(subject: str, paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Read a subject's fragments, keyed by step; all of them must exist."""
    missing = [step for step, path in paths.items() if not path.exists()]
    if missing:
        raise ProvenanceError(
            f"Missing fragments for sub-{subject}: {', '.join(missing)}"
        )
    return {
        step: json.loads(path.read_text(encoding="utf-8"))
        for step, path in paths.items()
    }


def write_runinfo(path: Path, subject: str, fragment_paths: dict[str, Path]) -> None:
    """Merge a subject's fragments into its runinfo.json."""
    merged = merge_fragments(subject, read_fragments(subject, fragment_paths))
    _write_json(path, merged)
