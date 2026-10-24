"""Run the openneuro-t1 pipeline: one step, or one subject end to end.

uv run openneuro-t1 --subject 01 [--force]
uv run openneuro-t1 --subject 01 --step bet [--force]
uv run openneuro-t1 --step template [--force]
"""

import argparse
import logging
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import anat, fetch, paths, provenance, qc, qc_index
from .config import load_config, project_path

PACKAGE_LOGGER = "openneuro_t1"


@dataclass(frozen=True)
class Context:
    """What one step needs: the config and the paths it reads and writes."""

    config: dict[str, Any]
    subject: str | None
    dataset: paths.DatasetPaths
    layout: paths.SubjectPaths | None
    logs: Path


@dataclass(frozen=True)
class Step:
    scope: str  # "dataset" runs once for everyone; "subject" runs per subject
    outputs: Callable[[Context], list[Path]]
    action: Callable[[Context], None]
    tools: tuple[str, ...] = ()  # NiWrap tools it runs, hence Docker images it uses


def _describe(ctx: Context) -> None:
    provenance.write_dataset_description(
        ctx.dataset.dataset_description,
        ctx.config["s3_uri"],
        ctx.dataset.raw_description,
    )
    anat.write_dseg_tsv(ctx.dataset.dseg_tsv)


def _qc_index(ctx: Context) -> None:
    qc_index.build_qc_index(
        subjects=ctx.config["subjects"],
        dataset=ctx.config["dataset"],
        version=provenance.pipeline_version(),
        raw=project_path(ctx.config["paths"]["raw"]),
        results=project_path(ctx.config["paths"]["results"]),
        template=ctx.config["template"],
        destination=ctx.dataset.qc_index,
    )


def _bet(ctx: Context) -> None:
    layout = ctx.layout
    anat.skull_strip(
        layout.raw_t1w, layout.brain, layout.mask, ctx.config["bet"]["frac"]
    )


def _fast(ctx: Context) -> None:
    layout = ctx.layout
    means = anat.segment(
        layout.brain, layout.dseg, layout.probseg, ctx.config["fast"]["classes"]
    )
    for kind, values in means.items():
        print(f"      mean T1 intensity by {kind}: {values}")


def _flirt(ctx: Context) -> None:
    layout = ctx.layout
    anat.register(
        layout.brain,
        ctx.dataset.template_brain,
        layout.registered,
        layout.matrix,
        ctx.config["flirt"]["dof"],
    )


def _qc(ctx: Context) -> None:
    layout = ctx.layout
    qc.skullstrip_figure(layout.raw_t1w, layout.mask, layout.skullstrip_png)
    qc.tissues_figure(layout.brain, layout.dseg, layout.tissues_png)
    qc.registration_figure(
        layout.registered, ctx.dataset.template_brain, layout.registration_png
    )


STEPS: dict[str, Step] = {
    "metadata": Step(
        "dataset",
        lambda ctx: [ctx.dataset.raw_description, ctx.dataset.raw_participants],
        lambda ctx: fetch.fetch_metadata(ctx.config),
    ),
    "template": Step(
        "dataset",
        lambda ctx: [ctx.dataset.template_brain],
        lambda ctx: fetch.fetch_template(ctx.config, force=True),
    ),
    "describe": Step(
        "dataset",
        lambda ctx: [ctx.dataset.dataset_description, ctx.dataset.dseg_tsv],
        _describe,
    ),
    "qc_index": Step("dataset", lambda ctx: [ctx.dataset.qc_index], _qc_index),
    "fetch": Step(
        "subject",
        lambda ctx: [ctx.layout.raw_t1w],
        lambda ctx: fetch.fetch_subject(ctx.subject, ctx.config),
    ),
    "bet": Step(
        "subject", lambda ctx: [ctx.layout.brain, ctx.layout.mask], _bet, ("bet",)
    ),
    "fast": Step(
        "subject",
        lambda ctx: [ctx.layout.dseg, *ctx.layout.probseg.values()],
        _fast,
        ("fast",),
    ),
    "flirt": Step(
        "subject",
        lambda ctx: [ctx.layout.registered, ctx.layout.matrix],
        _flirt,
        ("flirt",),
    ),
    "qc": Step(
        "subject",
        lambda ctx: [
            ctx.layout.skullstrip_png,
            ctx.layout.tissues_png,
            ctx.layout.registration_png,
        ],
        _qc,
    ),
    "runinfo": Step(
        "subject",
        lambda ctx: [ctx.layout.runinfo],
        lambda ctx: provenance.write_runinfo(
            ctx.layout.runinfo, ctx.subject, ctx.layout.fragments
        ),
    ),
}

# The order of a full subject run. qc_index is left out: it needs every subject.
FULL_RUN = (
    "metadata",
    "template",
    "fetch",
    "bet",
    "fast",
    "flirt",
    "qc",
    "describe",
    "runinfo",
)


def _context(config: dict[str, Any], subject: str | None) -> Context:
    raw = project_path(config["paths"]["raw"])
    results = project_path(config["paths"]["results"])
    template = config["template"]
    dataset = paths.dataset_paths(
        raw=raw,
        templates=project_path(config["paths"]["templates"]),
        results=results,
        template=template,
        resolution=config["template_resolution"],
    )
    layout = (
        paths.subject_paths(subject, raw=raw, results=results, template=template)
        if subject is not None
        else None
    )
    return Context(
        config, subject, dataset, layout, project_path(config["paths"]["logs"])
    )


@contextmanager
def _step_log(path: Path, logger_names: Iterable[str]) -> Iterator[None]:
    """Send the package's and NiWrap's runner logs to one step log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logging.getLogger(PACKAGE_LOGGER).setLevel(logging.INFO)
    loggers = [logging.getLogger(name) for name in logger_names]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()


def run_step(
    name: str,
    config: dict[str, Any] | None = None,
    subject: str | None = None,
    force: bool = False,
) -> bool:
    """Run one step unless all its outputs exist; return whether it ran.

    A subject step's provenance fragment is one of its outputs and is written
    last, so a step without its fragment is not finished.
    """
    config = config or load_config()
    step = STEPS[name]
    ctx = _context(config, subject)
    outputs = step.outputs(ctx)
    if name in paths.FRAGMENT_STEPS:
        outputs = [*outputs, ctx.layout.fragments[name]]
    label = name if subject is None else f"sub-{subject} {name}"
    if not force and all(output.exists() for output in outputs):
        print(f"[{label}] skipped: all outputs exist")
        return False

    print(f"[{label}] running")
    log_file = (
        paths.dataset_log_path(ctx.logs, name)
        if subject is None
        else paths.log_path(ctx.logs, subject, name)
    )
    started = datetime.now(UTC)
    begin = time.perf_counter()
    with ExitStack() as stack:
        logger_names = [PACKAGE_LOGGER]
        if step.tools:
            # NiWrap's scratch space; what is kept is copied out by anat.py.
            scratch = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="openneuro_t1_")
            )
            logger_names.append(anat.use_docker_runner(Path(scratch)).logger_name)
        stack.enter_context(_step_log(log_file, logger_names))
        step.action(ctx)
    seconds = round(time.perf_counter() - begin, 1)
    if name in paths.FRAGMENT_STEPS:
        images = (
            provenance.inspect_images(anat.container_images(step.tools))
            if step.tools
            else []
        )
        provenance.write_fragment(
            ctx.layout.fragments[name],
            subject,
            name,
            started,
            datetime.now(UTC),
            seconds,
            images,
        )
    print(f"[{label}] done in {seconds} s")
    return True


def run_subject(
    subject: str, force: bool = False, config: dict[str, Any] | None = None
) -> dict[str, bool]:
    """Run every step for one subject; return which steps ran.

    The merge is redone only when some step ran, so a run that skips everything
    leaves the existing runinfo.json, which describes the run that made the outputs.
    """
    config = config or load_config()
    ran: dict[str, bool] = {}
    for name in FULL_RUN:
        step_force = force or (name == "runinfo" and any(ran.values()))
        ran[name] = run_step(
            name,
            config,
            subject if STEPS[name].scope == "subject" else None,
            step_force,
        )
    return ran


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subject", help="subject label, e.g. 01")
    parser.add_argument(
        "--step",
        choices=list(STEPS),
        help="run one step instead of the whole subject; metadata, template, "
        "describe and qc_index are dataset-level and take no --subject",
    )
    parser.add_argument(
        "--force", action="store_true", help="redo steps whose outputs exist"
    )
    args = parser.parse_args(argv)

    if args.step is None:
        if args.subject is None:
            parser.error("--subject is required unless --step is a dataset step")
        run_subject(args.subject, force=args.force)
        return 0
    scope = STEPS[args.step].scope
    if scope == "subject" and args.subject is None:
        parser.error(f"--step {args.step} is a subject step and needs --subject")
    if scope == "dataset" and args.subject is not None:
        parser.error(f"--step {args.step} is a dataset step and takes no --subject")
    run_step(args.step, subject=args.subject, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
