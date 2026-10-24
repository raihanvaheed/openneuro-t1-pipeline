"""Download raw data from OpenNeuro on S3 and build the MNI template brain."""

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import nibabel as nib

from .config import load_config, project_path
from .paths import (
    atomic_output,
    raw_dataset_description_path,
    raw_participants_path,
    raw_t1w_path,
    template_brain_path,
)

log = logging.getLogger(__name__)


def sync_command(s3_uri: str, raw: Path, includes: list[str]) -> list[str]:
    """The anonymous `aws s3 sync` argument list that fetches only the given patterns."""
    command = [
        "aws",
        "s3",
        "sync",
        "--no-sign-request",
        f"{s3_uri}/",
        f"{raw}/",
        "--exclude",
        "*",
    ]
    for pattern in includes:
        command += ["--include", pattern]
    return command


def _sync(config: dict[str, Any], includes: list[str]) -> Path:
    """Run the sync into the raw dataset folder and return that folder."""
    raw = project_path(config["paths"]["raw"])
    raw.mkdir(parents=True, exist_ok=True)
    command = sync_command(config["s3_uri"], raw, includes)
    log.info("Command: %s", shlex.join(command))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    log.info("stdout:\n%s", result.stdout)
    log.info("stderr:\n%s", result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"aws s3 sync failed with exit code {result.returncode}")
    return raw


def fetch_metadata(config: dict[str, Any] | None = None) -> list[Path]:
    """Fetch the raw dataset_description.json and participants.tsv."""
    config = config or load_config()
    raw = project_path(config["paths"]["raw"])
    files = [raw_dataset_description_path(raw), raw_participants_path(raw)]
    _sync(config, [file.relative_to(raw).as_posix() for file in files])
    missing = [file for file in files if not file.exists()]
    if missing:
        raise FileNotFoundError(f"Not found after sync: {', '.join(map(str, missing))}")
    return files


def fetch_subject(subject: str, config: dict[str, Any] | None = None) -> Path:
    """Fetch one subject's T1w into the raw dataset folder and return its path."""
    config = config or load_config()
    raw = _sync(config, [f"sub-{subject}/anat/*T1w.nii.gz"])
    t1w = raw_t1w_path(raw, subject)
    if not t1w.exists():
        raise FileNotFoundError(f"No T1w image for sub-{subject} after sync: {t1w}")
    return t1w


def fetch_template(
    config: dict[str, Any] | None = None, *, force: bool = False
) -> Path:
    """Build the template brain (T1w times brain mask) from TemplateFlow.

    Does nothing if the template brain already exists, unless force is set.
    """
    config = config or load_config()
    template = config["template"]
    resolution = config["template_resolution"]
    brain = template_brain_path(
        project_path(config["paths"]["templates"]), template, resolution
    )
    if brain.exists() and not force:
        log.info("Template brain exists: %s", brain)
        return brain

    # TemplateFlow reads TEMPLATEFLOW_HOME when it is imported, so set it first.
    home = project_path(config["paths"]["templateflow"])
    os.environ["TEMPLATEFLOW_HOME"] = str(home)
    from templateflow import api as templateflow
    from templateflow import conf as templateflow_conf

    if Path(templateflow_conf.TF_HOME).resolve() != home.resolve():
        raise RuntimeError(
            f"TemplateFlow was imported with {templateflow_conf.TF_HOME}, not {home}"
        )

    t1w = templateflow.get(
        template, resolution=resolution, desc=None, suffix="T1w", extension="nii.gz"
    )
    mask = templateflow.get(
        template, resolution=resolution, desc="brain", suffix="mask", extension="nii.gz"
    )
    log.info("Template T1w: %s", t1w)
    log.info("Template brain mask: %s", mask)

    t1w_image = nib.load(t1w)
    mask_image = nib.load(mask)
    data = t1w_image.get_fdata(dtype="float32") * (mask_image.get_fdata() > 0)
    brain_image = nib.Nifti1Image(
        data.astype("float32"), t1w_image.affine, t1w_image.header
    )
    brain_image.set_data_dtype("float32")
    with atomic_output(brain) as partial:
        nib.save(brain_image, partial)
    log.info("Wrote template brain: %s", brain)
    return brain
