"""FSL BET, FAST and FLIRT through NiWrap's Docker runner."""

import importlib
import logging
import shutil
from collections.abc import Iterable
from pathlib import Path

import nibabel as nib
import niwrap
from niwrap import fsl

from .paths import TISSUE_LABELS, atomic_output

log = logging.getLogger(__name__)

# Label values 1, 2, 3 in the dseg image, and FAST partial-volume outputs 0, 1, 2.
TISSUES = TISSUE_LABELS

FAST_T1 = 1  # FAST image type: 1 = T1
FAST_BASENAME = "fast"
FLIRT_OUT_FILE = "registered.nii.gz"
FLIRT_OUT_MATRIX = "t1w_to_template.mat"

_TOOL_METADATA = {
    "bet": ("niwrap.fsl.bet", "BET_METADATA"),
    "fast": ("niwrap.fsl.fast", "FAST_METADATA"),
    "flirt": ("niwrap.fsl.flirt", "FLIRT_METADATA"),
}


class ClassOrderError(RuntimeError):
    """FAST's classes are not in CSF, GM, WM order of rising T1 intensity."""


def use_docker_runner(data_dir: Path) -> niwrap.Runner:
    """Make NiWrap's Docker runner the global runner. The only place one is set.

    The console shows one line per tool call; the full command, stdout and
    stderr stay at DEBUG for the per-step log files.
    """
    runner = niwrap.use_docker(data_dir=data_dir)
    for handler in runner.logger.handlers:
        handler.setLevel(logging.INFO)
    return runner


def container_images(tools: Iterable[str]) -> list[str]:
    """Docker image tags NiWrap runs the given tools in, from its tool metadata."""
    tags = set()
    for tool in tools:
        module, attribute = _TOOL_METADATA[tool]
        tags.add(
            getattr(importlib.import_module(module), attribute).container_image_tag
        )
    return sorted(tags)


def _copy(source: Path, destination: Path) -> None:
    with atomic_output(destination) as partial:
        shutil.copy2(source, partial)
    log.info("Wrote %s", destination)


def skull_strip(
    t1w: Path,
    brain: Path,
    mask: Path,
    frac: float,
    runner: niwrap.Runner | None = None,
) -> None:
    """FSL BET on the raw T1w: writes the brain image and its binary mask."""
    log.info("BET: %s -> %s, %s", t1w, brain, mask)
    bet = fsl.bet(
        infile=t1w, fractional_intensity=frac, binary_mask=True, runner=runner
    )
    _copy(bet.outfile, brain)
    _copy(bet.binary_mask, mask)


def segment(
    brain: Path,
    dseg: Path,
    probseg: dict[str, Path],
    classes: int,
    runner: niwrap.Runner | None = None,
) -> dict[str, dict[str, float]]:
    """FSL FAST on the BET brain: writes the label image and the three PVE maps.

    probseg maps each name in TISSUES to its destination. Before anything is
    written, the mean T1 intensity of each class is checked to rise from CSF to
    GM to WM, and the class means are returned.
    """
    if classes != len(TISSUES):
        raise ValueError(
            f"Labels are defined for {len(TISSUES)} classes, not {classes}"
        )
    log.info("FAST: %s -> %s, %s", brain, dseg, ", ".join(map(str, probseg.values())))
    fast = fsl.fast(
        in_files=[brain],
        number_classes=classes,
        img_type=FAST_T1,
        out_basename=FAST_BASENAME,
        runner=runner,
    )
    # NiWrap names no output for the per-class partial-volume images.
    pve = [fast.root / f"{FAST_BASENAME}_pve_{i}.nii.gz" for i in range(classes)]
    means = check_class_order(brain, fast.tissue_class_map, pve)
    for line, values in means.items():
        log.info("Mean T1 intensity by %s: %s", line, values)
    _copy(fast.tissue_class_map, dseg)
    for name, source in zip(TISSUES, pve):
        _copy(source, probseg[name])
    return means


def check_class_order(
    brain: Path, seg: Path, pve: list[Path]
) -> dict[str, dict[str, float]]:
    """Require mean T1 intensity to rise CSF < GM < WM, by label and by PVE map."""
    t1 = nib.load(brain).get_fdata()
    labels = nib.load(seg).get_fdata()
    by_label = [float(t1[labels == i + 1].mean()) for i in range(len(TISSUES))]
    by_pve = []
    for path in pve:
        weights = nib.load(path).get_fdata()
        by_pve.append(float((t1 * weights).sum() / weights.sum()))
    means = {
        "dseg label": dict(zip(TISSUES, by_label)),
        "partial-volume map": dict(zip(TISSUES, by_pve)),
    }
    for kind, values in means.items():
        ordered = list(values.values())
        if not ordered[0] < ordered[1] < ordered[2]:
            raise ClassOrderError(
                f"Mean T1 intensity by {kind} does not rise CSF < GM < WM: {values}"
            )
    return means


def write_dseg_tsv(path: Path) -> None:
    """The label table for the dseg image: index and name, one row per tissue."""
    rows = ["index\tname", *(f"{i}\t{name}" for i, name in enumerate(TISSUES, 1))]
    with atomic_output(path) as partial:
        partial.write_text("\n".join(rows) + "\n", encoding="utf-8")


def register(
    brain: Path,
    template_brain: Path,
    registered: Path,
    matrix: Path,
    dof: int,
    runner: niwrap.Runner | None = None,
) -> None:
    """FSL FLIRT, BET brain to template brain, default cost function."""
    log.info("FLIRT: %s -> %s, %s", brain, registered, matrix)
    flirt = fsl.flirt(
        in_file=brain,
        reference=template_brain,
        out_file=FLIRT_OUT_FILE,
        out_matrix_file=FLIRT_OUT_MATRIX,
        dof=dof,
        runner=runner,
    )
    _copy(flirt.out_file, registered)
    _copy(flirt.out_matrix_file, matrix)
