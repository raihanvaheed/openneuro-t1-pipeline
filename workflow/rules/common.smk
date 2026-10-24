from pathlib import Path

from openneuro_t1 import paths

# Rules get every path from openneuro_t1.paths. Called with this placeholder,
# the paths hold a Snakemake wildcard.
SUBJECT = paths.SUBJECT_PLACEHOLDER


def dataset_layout():
    return paths.dataset_paths(
        raw=Path(config["paths"]["raw"]),
        templates=Path(config["paths"]["templates"]),
        results=Path(config["paths"]["results"]),
        template=config["template"],
        resolution=config["template_resolution"],
    )


def subject_layout(subject=SUBJECT):
    return paths.subject_paths(
        subject,
        raw=Path(config["paths"]["raw"]),
        results=Path(config["paths"]["results"]),
        template=config["template"],
    )


def step_log(step, subject=None):
    logs = Path(config["paths"]["logs"])
    if subject is None:
        return paths.dataset_log_path(logs, step)
    return paths.log_path(logs, subject, step)


def memory(step):
    return config["mem_mb"].get(step, config["mem_mb"]["default"])


def qc_index_inputs():
    """Every configured subject's QC images and merged provenance."""
    files = []
    for subject in config["subjects"]:
        layout = subject_layout(subject)
        files += [
            layout.skullstrip_png,
            layout.tissues_png,
            layout.registration_png,
            layout.runinfo,
        ]
    return files
