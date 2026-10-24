"""The only place output filenames are made: BIDS derivative paths."""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_LABEL = re.compile(r"[A-Za-z0-9]+")

# Snakemake rules pass this as the subject, so the paths they get hold a wildcard.
SUBJECT_PLACEHOLDER = "{subject}"

# Tissue names in the order of FAST's classes and the values 1, 2, 3 in the dseg image.
TISSUE_LABELS = ("CSF", "GM", "WM")

# Subject steps that write a provenance fragment, in the order they run.
FRAGMENT_STEPS = ("fetch", "bet", "fast", "flirt", "qc")

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
        if not (key == "sub" and value == SUBJECT_PLACEHOLDER) and not _LABEL.fullmatch(
            value
        ):
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


def dataset_log_path(logs: Path, step: str) -> Path:
    return logs / f"{step}.log"


def fragment_path(results: Path, subject: str, step: str) -> Path:
    """One subject step's provenance record: results/provenance/sub-<id>/<step>.json."""
    return results / "provenance" / f"sub-{subject}" / f"{step}.json"


def qc_index_path(results: Path) -> Path:
    return results / "qc" / "index.html"


def raw_dataset_description_path(raw: Path) -> Path:
    return raw / "dataset_description.json"


def raw_participants_path(raw: Path) -> Path:
    return raw / "participants.tsv"


def template_brain_path(templates: Path, template: str, resolution: int) -> Path:
    return templates / f"tpl-{template}_res-{resolution:02d}_desc-brain_T1w.nii.gz"


def raw_t1w_path(raw: Path, subject: str) -> Path:
    """The subject's raw T1w, or the BIDS name where it is expected if absent."""
    anat = raw / f"sub-{subject}" / "anat"
    matches = sorted(anat.glob("*T1w.nii.gz"))
    if len(matches) > 1:
        raise ValueError(f"Expected one T1w image in {anat}, found {len(matches)}")
    return matches[0] if matches else anat / f"sub-{subject}_T1w.nii.gz"


@dataclass(frozen=True)
class DatasetPaths:
    """Files every subject shares; each is made by one dataset-level step."""

    raw_description: Path
    raw_participants: Path
    template_brain: Path
    dataset_description: Path
    dseg_tsv: Path
    qc_index: Path


def dataset_paths(
    *, raw: Path, templates: Path, results: Path, template: str, resolution: int
) -> DatasetPaths:
    return DatasetPaths(
        raw_description=raw_dataset_description_path(raw),
        raw_participants=raw_participants_path(raw),
        template_brain=template_brain_path(templates, template, resolution),
        dataset_description=dataset_description_path(results),
        dseg_tsv=dseg_tsv_path(results),
        qc_index=qc_index_path(results),
    )


@dataclass(frozen=True)
class SubjectPaths:
    """Every file one subject's steps read or write."""

    subject: str
    raw_t1w: Path
    brain: Path
    mask: Path
    dseg: Path
    probseg: dict[str, Path]  # by tissue name, in TISSUE_LABELS order
    registered: Path
    matrix: Path
    skullstrip_png: Path
    tissues_png: Path
    registration_png: Path
    fragments: dict[str, Path]  # by step, in FRAGMENT_STEPS order
    runinfo: Path


def subject_paths(
    subject: str, *, raw: Path, results: Path, template: str
) -> SubjectPaths:
    """The layout for one subject; pass SUBJECT_PLACEHOLDER for a Snakemake wildcard."""

    def derivative(suffix: str, extension: str, **entities: str) -> Path:
        return derivative_path(results, subject, suffix, extension, **entities)

    return SubjectPaths(
        subject=subject,
        raw_t1w=raw_t1w_path(raw, subject),
        brain=derivative("T1w", ".nii.gz", desc="brain"),
        mask=derivative("mask", ".nii.gz", desc="brain"),
        dseg=derivative("dseg", ".nii.gz"),
        probseg={
            label: derivative("probseg", ".nii.gz", label=label)
            for label in TISSUE_LABELS
        },
        registered=derivative("T1w", ".nii.gz", space=template, desc="brain"),
        matrix=derivative("xfm", ".mat", from_="T1w", to=template, mode="image"),
        skullstrip_png=derivative("T1w", ".png", desc="skullstrip", datatype="figures"),
        tissues_png=derivative("dseg", ".png", desc="tissues", datatype="figures"),
        registration_png=derivative(
            "T1w", ".png", space=template, desc="registration", datatype="figures"
        ),
        fragments={
            step: fragment_path(results, subject, step) for step in FRAGMENT_STEPS
        },
        runinfo=runinfo_path(results, subject),
    )


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
