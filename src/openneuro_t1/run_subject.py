"""Run one subject end to end: fetch, template, BET, FAST, FLIRT, QC.

uv run python3 -m openneuro_t1.run_subject --subject 01 [--force]
"""

import argparse
import logging
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import anat, fetch, paths, provenance, qc
from .config import load_config, project_path

PACKAGE_LOGGER = "openneuro_t1"


@contextmanager
def _step_log(path: Path, runner_logger: str) -> Iterator[None]:
    """Send the package's and NiWrap's runner logs to one step log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    package = logging.getLogger(PACKAGE_LOGGER)
    package.setLevel(logging.INFO)
    loggers = [package, logging.getLogger(runner_logger)]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()


def run_subject(
    subject: str, force: bool = False, config: dict[str, Any] | None = None
) -> None:
    config = config or load_config()
    raw = project_path(config["paths"]["raw"])
    results = project_path(config["paths"]["results"])
    logs = project_path(config["paths"]["logs"])
    space = config["template"]
    template_brain = paths.template_brain_path(
        project_path(config["paths"]["templates"]),
        space,
        config["template_resolution"],
    )

    def derivative(suffix: str, extension: str, **entities: str) -> Path:
        return paths.derivative_path(results, subject, suffix, extension, **entities)

    brain = derivative("T1w", ".nii.gz", desc="brain")
    mask = derivative("mask", ".nii.gz", desc="brain")
    dseg = derivative("dseg", ".nii.gz")
    probseg = {
        name: derivative("probseg", ".nii.gz", label=name) for name in anat.TISSUES
    }
    registered = derivative("T1w", ".nii.gz", space=space, desc="brain")
    matrix = derivative("xfm", ".mat", from_="T1w", to=space, mode="image")
    skullstrip_png = derivative("T1w", ".png", desc="skullstrip", datatype="figures")
    tissues_png = derivative("dseg", ".png", desc="tissues", datatype="figures")
    registration_png = derivative(
        "T1w", ".png", space=space, desc="registration", datatype="figures"
    )

    def raw_t1w() -> Path:
        return paths.raw_t1w_path(raw, subject)

    def fast_step() -> None:
        means = anat.segment(brain, dseg, probseg, config["fast"]["classes"])
        for kind, values in means.items():
            print(f"      mean T1 intensity by {kind}: {values}")

    def qc_step() -> None:
        qc.skullstrip_figure(raw_t1w(), mask, skullstrip_png)
        qc.tissues_figure(brain, dseg, tissues_png)
        qc.registration_figure(registered, template_brain, registration_png)

    # (name, outputs, action); a step is finished when all its outputs exist.
    steps: list[tuple[str, list[Path], Callable[[], object]]] = [
        (
            "fetch",
            [raw_t1w(), *(raw / name for name in fetch.DATASET_FILES)],
            lambda: fetch.fetch_subject(subject, config),
        ),
        (
            "template",
            [template_brain],
            lambda: fetch.fetch_template(config, force=force),
        ),
        (
            "bet",
            [brain, mask],
            lambda: anat.skull_strip(raw_t1w(), brain, mask, config["bet"]["frac"]),
        ),
        ("fast", [dseg, *probseg.values()], fast_step),
        (
            "flirt",
            [registered, matrix],
            lambda: anat.register(
                brain, template_brain, registered, matrix, config["flirt"]["dof"]
            ),
        ),
        ("qc", [skullstrip_png, tissues_png, registration_png], qc_step),
    ]

    started = datetime.now(UTC)
    report: dict[str, dict[str, Any]] = {}
    # NiWrap's scratch space; what is kept is copied out by anat.py.
    with tempfile.TemporaryDirectory(prefix="openneuro_t1_") as scratch:
        runner = anat.use_docker_runner(Path(scratch))
        for name, outputs, action in steps:
            if not force and all(output.exists() for output in outputs):
                report[name] = {"status": "skipped", "seconds": None}
                print(f"[{name}] skipped: all outputs exist")
                continue
            print(f"[{name}] running")
            begin = time.perf_counter()
            with _step_log(paths.log_path(logs, subject, name), runner.logger_name):
                action()
            seconds = round(time.perf_counter() - begin, 1)
            report[name] = {"status": "ran", "seconds": seconds}
            print(f"[{name}] done in {seconds} s")
    finished = datetime.now(UTC)

    description = paths.dataset_description_path(results)
    dseg_tsv = paths.dseg_tsv_path(results)
    if force or not description.exists():
        provenance.write_dataset_description(
            description, config["s3_uri"], raw / "dataset_description.json"
        )
    if force or not dseg_tsv.exists():
        anat.write_dseg_tsv(dseg_tsv)

    # A rerun that skipped everything keeps the record of the run that made the outputs.
    ran = [name for name, entry in report.items() if entry["status"] == "ran"]
    if not ran:
        print("Nothing ran; runinfo left as it was.")
        return
    tools = [name for name in ("bet", "fast", "flirt") if name in ran]
    provenance.write_runinfo(
        paths.runinfo_path(results, subject),
        subject,
        started,
        finished,
        report,
        provenance.inspect_images(anat.container_images(tools)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subject", required=True, help="subject label, e.g. 01")
    parser.add_argument(
        "--force", action="store_true", help="redo steps whose outputs exist"
    )
    args = parser.parse_args(argv)
    run_subject(args.subject, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
