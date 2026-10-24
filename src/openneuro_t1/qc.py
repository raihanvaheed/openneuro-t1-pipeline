"""Quality-check images: three orthogonal views per processing step."""

import logging
from pathlib import Path

import matplotlib
from matplotlib.colors import ListedColormap
from nilearn import plotting

from .paths import atomic_output

matplotlib.use("Agg")

log = logging.getLogger(__name__)

# Colours for dseg labels 1, 2, 3 (CSF, GM, WM).
TISSUE_COLORS = ("tab:blue", "tab:green", "tab:red")

# nilearn dims the background image by default, which hides the skull and neck.
BACKGROUND_DIM = -1


def _save(display, destination: Path) -> None:
    try:
        with atomic_output(destination) as partial:
            display.savefig(partial, dpi=150)
    finally:
        display.close()
    log.info("Wrote %s", destination)


def skullstrip_figure(t1w: Path, mask: Path, destination: Path) -> None:
    """The raw T1w with the outline of the brain mask drawn on."""
    display = plotting.plot_anat(
        t1w,
        cut_coords=plotting.find_xyz_cut_coords(mask),
        draw_cross=False,
        colorbar=False,
        dim=BACKGROUND_DIM,
        title="Skull strip: brain mask outline on the raw T1w",
    )
    display.add_contours(mask, levels=[0.5], colors="r", linewidths=1)
    _save(display, destination)


def tissues_figure(brain: Path, dseg: Path, destination: Path) -> None:
    """The BET brain with the dseg labels overlaid."""
    display = plotting.plot_roi(
        dseg,
        bg_img=brain,
        cut_coords=plotting.find_xyz_cut_coords(dseg, activation_threshold=0.5),
        draw_cross=False,
        colorbar=False,
        cmap=ListedColormap(TISSUE_COLORS),
        vmin=0.5,
        vmax=3.5,
        alpha=0.5,
        dim=BACKGROUND_DIM,
        title="Tissues on the BET brain: CSF blue, GM green, WM red",
    )
    _save(display, destination)


def registration_figure(
    registered: Path, template_brain: Path, destination: Path
) -> None:
    """The registered brain with the edges of the template brain drawn on."""
    display = plotting.plot_anat(
        registered,
        cut_coords=plotting.find_xyz_cut_coords(template_brain),
        draw_cross=False,
        colorbar=False,
        dim=BACKGROUND_DIM,
        title="Registration: template brain edges on the registered brain",
    )
    display.add_edges(template_brain, color="r")
    _save(display, destination)
