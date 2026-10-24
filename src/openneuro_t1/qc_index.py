"""A one-page index of every subject's QC images and step timings."""

import html
import json
import logging
import os
from pathlib import Path

from .paths import FRAGMENT_STEPS, atomic_output, subject_paths

log = logging.getLogger(__name__)

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: 0.25rem 0.75rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
.figures { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); }
figure { margin: 0; }
img { max-width: 100%; }
"""


class QcIndexError(RuntimeError):
    """Files the index needs are missing."""


def build_qc_index(
    *,
    subjects: list[str],
    dataset: str,
    version: str,
    raw: Path,
    results: Path,
    template: str,
    destination: Path,
) -> None:
    """Write the index page for every subject, or fail naming what is missing."""
    layouts = [
        subject_paths(subject, raw=raw, results=results, template=template)
        for subject in subjects
    ]
    missing = []
    for layout in layouts:
        needed = [
            layout.skullstrip_png,
            layout.tissues_png,
            layout.registration_png,
            layout.runinfo,
        ]
        absent = [str(path) for path in needed if not path.exists()]
        if absent:
            missing.append(f"sub-{layout.subject}: {', '.join(absent)}")
    if missing:
        raise QcIndexError(
            "The QC index needs files that are missing: " + "; ".join(missing)
        )

    runinfos = {
        layout.subject: json.loads(layout.runinfo.read_text(encoding="utf-8"))
        for layout in layouts
    }
    images: dict[str, dict[str, str]] = {}
    for runinfo in runinfos.values():
        for image in runinfo["docker_images"]:
            images.setdefault(image["digest"], image)

    def link(path: Path) -> str:
        return html.escape(
            Path(os.path.relpath(path, destination.parent)).as_posix(), quote=True
        )

    rows = "".join(
        "<tr>"
        + f"<td>sub-{html.escape(layout.subject)}</td>"
        + "".join(
            f"<td>{html.escape(str(runinfos[layout.subject]['steps'][step]['seconds']))}</td>"
            for step in FRAGMENT_STEPS
        )
        + "</tr>"
        for layout in layouts
    )
    sections = ""
    for layout in layouts:
        figures = (
            ("Skull strip", layout.skullstrip_png),
            ("Tissues", layout.tissues_png),
            ("Registration", layout.registration_png),
        )
        sections += (
            f"<section><h3>sub-{html.escape(layout.subject)}</h3>"
            '<div class="figures">'
            + "".join(
                f'<figure><a href="{link(path)}">'
                f'<img src="{link(path)}" alt="{html.escape(title)}, sub-{html.escape(layout.subject)}">'
                f"</a><figcaption>{html.escape(title)}</figcaption></figure>"
                for title, path in figures
            )
            + "</div></section>"
        )
    digests = "; ".join(
        html.escape(f"{image['tag']} {image['digest']}") for image in images.values()
    )
    header = "".join(f"<th>{html.escape(step)}</th>" for step in FRAGMENT_STEPS)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>QC index</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>QC index</h1>"
        f"<p>Pipeline version {html.escape(version)}. Dataset {html.escape(dataset)}. "
        f"Docker images: {digests}.</p>"
        "<p>These images are for visual review; this page makes no judgement on them.</p>"
        "<h2>Seconds per step</h2>"
        f"<table><tr><th>subject</th>{header}</tr>{rows}</table>"
        f"<h2>Images</h2>{sections}</body></html>\n"
    )
    with atomic_output(destination) as partial:
        partial.write_text(page, encoding="utf-8")
    log.info("Wrote %s", destination)
