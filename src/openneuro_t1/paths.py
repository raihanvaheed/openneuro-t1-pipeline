"""The only place output filenames are made: BIDS derivative paths."""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LABEL = re.compile(r"[A-Za-z0-9]+")

# BIDS entity order. from/to/mode are the transform entities; they never occur
# together with space/label/desc in this pipeline.
_ENTITY_ORDER = ("sub", "from", "to", "mode", "space", "label", "desc")


def derivative_path(
    results: Path,
    subject: str,
    suffix: str,
    extension: str,
    *,
    space: str | None = None,
    desc: str | None = None,
    label: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    mode: str | None = None,
    datatype: str = "anat",
) -> Path:
    """Build results/sub-<id>/<datatype>/sub-<id>_<entities>_<suffix><extension>."""
    entities = {
        "sub": subject,
        "from": from_,
        "to": to,
        "mode": mode,
        "space": space,
        "label": label,
        "desc": desc,
    }
    parts = []
    for key in _ENTITY_ORDER:
        value = entities[key]
        if value is None:
            continue
        if not _LABEL.fullmatch(value):
            raise ValueError(f"BIDS label for {key!r} must be alphanumeric: {value!r}")
        parts.append(f"{key}-{value}")
    if not _LABEL.fullmatch(suffix):
        raise ValueError(f"BIDS suffix must be alphanumeric: {suffix!r}")
    filename = "_".join([*parts, suffix]) + extension
    return results / f"sub-{subject}" / datatype / filename


def dataset_description_path(results: Path) -> Path:
    return results / "dataset_description.json"


def dseg_tsv_path(results: Path) -> Path:
    return results / "dseg.tsv"


def runinfo_path(results: Path, subject: str) -> Path:
    return results / "provenance" / f"sub-{subject}_runinfo.json"


def log_path(logs: Path, subject: str, step: str) -> Path:
    return logs / f"sub-{subject}" / f"{step}.log"


def template_brain_path(templates: Path, template: str, resolution: int) -> Path:
    return templates / f"tpl-{template}_res-{resolution:02d}_desc-brain_T1w.nii.gz"


def raw_t1w_path(raw: Path, subject: str) -> Path:
    """The subject's raw T1w, or the BIDS name where it is expected if absent."""
    anat = raw / f"sub-{subject}" / "anat"
    matches = sorted(anat.glob("*T1w.nii.gz"))
    if len(matches) > 1:
        raise ValueError(f"Expected one T1w image in {anat}, found {len(matches)}")
    return matches[0] if matches else anat / f"sub-{subject}_T1w.nii.gz"


@contextmanager
def atomic_output(destination: Path) -> Iterator[Path]:
    """Yield a sibling path to write to; move it onto destination only on success.

    A file at its final name is therefore always complete, so a step that is
    interrupted never leaves a truncated output that a rerun would skip.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    stem, dot, extension = destination.name.partition(".")
    partial = destination.with_name(f"{stem}.part{dot}{extension}")
    try:
        yield partial
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
