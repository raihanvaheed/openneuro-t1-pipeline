"""Download a subject's T1w from OpenNeuro on S3 and build the MNI template brain."""

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import nibabel as nib

from .config import load_config, project_path
from .paths import atomic_output, raw_t1w_path, template_brain_path

log = logging.getLogger(__name__)

DATASET_FILES = ("dataset_description.json", "participants.tsv")


def sync_command(subject: str, s3_uri: str, raw: Path) -> list[str]:
    """The anonymous `aws s3 sync` argument list for one subject's T1w.

    The dataset metadata files are added only while they are missing, so a
    finished download syncs nothing.
    """
    command = [
        "aws",
        "s3",
        "sync",
        "--no-sign-request",
        f"{s3_uri}/",
        f"{raw}/",
        "--exclude",
        "*",
        "--include",
        f"sub-{subject}/anat/*T1w.nii.gz",
    ]
    for name in DATASET_FILES:
        if not (raw / name).exists():
            command += ["--include", name]
    return command


def fetch_subject(subject: str, config: dict[str, Any] | None = None) -> Path:
    """Sync one subject's T1w into the raw dataset folder and return its path."""
    config = config or load_config()
    raw = project_path(config["paths"]["raw"])
    raw.mkdir(parents=True, exist_ok=True)
    command = sync_command(subject, config["s3_uri"], raw)
    log.info("Command: %s", shlex.join(command))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    log.info("stdout:\n%s", result.stdout)
    log.info("stderr:\n%s", result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"aws s3 sync failed with exit code {result.returncode}")
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
