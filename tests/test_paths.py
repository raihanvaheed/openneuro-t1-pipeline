from dataclasses import fields
from pathlib import Path

import pytest

from openneuro_t1 import paths

RESULTS = Path("results")
SPACE = "MNI152NLin2009cAsym"

# (suffix, extension, entities, expected path under results/)
DERIVATIVES = [
    ("T1w", ".nii.gz", {"desc": "brain"}, "sub-01/anat/sub-01_desc-brain_T1w.nii.gz"),
    ("mask", ".nii.gz", {"desc": "brain"}, "sub-01/anat/sub-01_desc-brain_mask.nii.gz"),
    ("dseg", ".nii.gz", {}, "sub-01/anat/sub-01_dseg.nii.gz"),
    (
        "probseg",
        ".nii.gz",
        {"label": "CSF"},
        "sub-01/anat/sub-01_label-CSF_probseg.nii.gz",
    ),
    (
        "probseg",
        ".nii.gz",
        {"label": "GM"},
        "sub-01/anat/sub-01_label-GM_probseg.nii.gz",
    ),
    (
        "probseg",
        ".nii.gz",
        {"label": "WM"},
        "sub-01/anat/sub-01_label-WM_probseg.nii.gz",
    ),
    (
        "T1w",
        ".nii.gz",
        {"space": SPACE, "desc": "brain"},
        f"sub-01/anat/sub-01_space-{SPACE}_desc-brain_T1w.nii.gz",
    ),
    (
        "xfm",
        ".mat",
        {"from_": "T1w", "to": SPACE, "mode": "image"},
        f"sub-01/anat/sub-01_from-T1w_to-{SPACE}_mode-image_xfm.mat",
    ),
    (
        "T1w",
        ".png",
        {"desc": "skullstrip", "datatype": "figures"},
        "sub-01/figures/sub-01_desc-skullstrip_T1w.png",
    ),
    (
        "dseg",
        ".png",
        {"desc": "tissues", "datatype": "figures"},
        "sub-01/figures/sub-01_desc-tissues_dseg.png",
    ),
    (
        "T1w",
        ".png",
        {"space": SPACE, "desc": "registration", "datatype": "figures"},
        f"sub-01/figures/sub-01_space-{SPACE}_desc-registration_T1w.png",
    ),
]


@pytest.mark.parametrize(("suffix", "extension", "entities", "expected"), DERIVATIVES)
def test_derivative_filenames(suffix, extension, entities, expected):
    assert paths.derivative_path(
        RESULTS, "01", suffix, extension, **entities
    ) == RESULTS / Path(expected)


def test_entities_follow_bids_order_whatever_the_keyword_order():
    first = paths.derivative_path(
        RESULTS, "01", "T1w", ".nii.gz", desc="brain", label="GM", space=SPACE
    )
    second = paths.derivative_path(
        RESULTS, "01", "T1w", ".nii.gz", space=SPACE, label="GM", desc="brain"
    )
    assert first == second
    assert first.name == f"sub-01_space-{SPACE}_label-GM_desc-brain_T1w.nii.gz"


@pytest.mark.parametrize("bad", ["bra-in", "bra_in", "", "a b"])
def test_non_alphanumeric_labels_are_rejected(bad):
    with pytest.raises(ValueError):
        paths.derivative_path(RESULTS, "01", "T1w", ".nii.gz", desc=bad)


def test_dataset_level_paths():
    assert paths.dataset_description_path(RESULTS) == Path(
        "results/dataset_description.json"
    )
    assert paths.dseg_tsv_path(RESULTS) == Path("results/dseg.tsv")
    assert paths.runinfo_path(RESULTS, "01") == Path(
        "results/provenance/sub-01_runinfo.json"
    )


@pytest.mark.parametrize("step", ["bet", "fast", "flirt", "qc"])
def test_log_paths(step):
    assert paths.log_path(Path("logs"), "01", step) == Path(f"logs/sub-01/{step}.log")


def test_template_brain_path():
    assert paths.template_brain_path(Path("resources/templates"), SPACE, 1) == Path(
        f"resources/templates/tpl-{SPACE}_res-01_desc-brain_T1w.nii.gz"
    )


def test_raw_t1w_path(tmp_path):
    expected = tmp_path / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
    assert paths.raw_t1w_path(tmp_path, "01") == expected  # absent: where expected
    expected.parent.mkdir(parents=True)
    expected.touch()
    assert paths.raw_t1w_path(tmp_path, "01") == expected
    (expected.parent / "sub-01_acq-extra_T1w.nii.gz").touch()
    with pytest.raises(ValueError):
        paths.raw_t1w_path(tmp_path, "01")


def test_atomic_output_moves_into_place_on_success(tmp_path):
    destination = tmp_path / "deep" / "sub-01_desc-brain_mask.nii.gz"
    with paths.atomic_output(destination) as partial:
        assert partial != destination
        assert partial.name.endswith(".nii.gz")  # keeps the extension for writers
        partial.write_text("done")
        assert not destination.exists()
    assert destination.read_text() == "done"
    assert sorted(p.name for p in destination.parent.iterdir()) == [destination.name]


def test_atomic_output_leaves_nothing_on_failure(tmp_path):
    destination = tmp_path / "out.nii.gz"
    with pytest.raises(RuntimeError), paths.atomic_output(destination) as partial:
        partial.write_text("half")
        raise RuntimeError("tool failed")
    assert list(tmp_path.iterdir()) == []


def test_atomic_output_keeps_the_previous_file_on_failure(tmp_path):
    destination = tmp_path / "out.nii.gz"
    destination.write_text("previous")
    with pytest.raises(RuntimeError), paths.atomic_output(destination) as partial:
        partial.write_text("half")
        raise RuntimeError("tool failed")
    assert destination.read_text() == "previous"


def format_for(value, subject):
    """A layout built with the placeholder, with the placeholder filled in."""
    if isinstance(value, Path):
        return Path(str(value).format(subject=subject))
    if isinstance(value, dict):
        return {key: format_for(item, subject) for key, item in value.items()}
    if isinstance(value, str):
        return value.format(subject=subject)
    return value


def test_subject_layout_with_the_placeholder_matches_a_real_subject():
    raw = Path("resources/ds000102")
    placeholder = paths.subject_paths(
        paths.SUBJECT_PLACEHOLDER, raw=raw, results=RESULTS, template=SPACE
    )
    real = paths.subject_paths("01", raw=raw, results=RESULTS, template=SPACE)

    for field in fields(real):
        assert format_for(getattr(placeholder, field.name), "01") == getattr(
            real, field.name
        ), field.name
    assert "{subject}" in str(placeholder.brain)


def test_single_file_paths_with_the_placeholder_match_a_real_subject():
    for build in (
        lambda s: paths.runinfo_path(RESULTS, s),
        lambda s: paths.fragment_path(RESULTS, s, "bet"),
        lambda s: paths.log_path(Path("logs"), s, "bet"),
        lambda s: paths.raw_t1w_path(Path("raw"), s),
    ):
        assert format_for(build("{subject}"), "01") == build("01")


@pytest.mark.parametrize("bad", ["{other}", "{subject}x", "{subject}{subject}"])
def test_only_the_exact_subject_placeholder_is_allowed(bad):
    with pytest.raises(ValueError):
        paths.derivative_path(RESULTS, bad, "T1w", ".nii.gz")


def test_the_placeholder_is_only_allowed_as_the_subject():
    with pytest.raises(ValueError):
        paths.derivative_path(RESULTS, "01", "T1w", ".nii.gz", desc="{subject}")


def test_subject_layout_holds_the_fragments_of_the_five_subject_steps():
    layout = paths.subject_paths("01", raw=Path("raw"), results=RESULTS, template=SPACE)

    assert list(layout.fragments) == ["fetch", "bet", "fast", "flirt", "qc"]
    assert layout.fragments["bet"] == Path("results/provenance/sub-01/bet.json")
    assert list(layout.probseg) == ["CSF", "GM", "WM"]
    assert layout.runinfo == Path("results/provenance/sub-01_runinfo.json")


def test_dataset_layout_names_the_files_every_subject_shares():
    layout = paths.dataset_paths(
        raw=Path("resources/ds000102"),
        templates=Path("resources/templates"),
        results=RESULTS,
        template=SPACE,
        resolution=1,
    )

    assert layout.raw_description == Path("resources/ds000102/dataset_description.json")
    assert layout.raw_participants == Path("resources/ds000102/participants.tsv")
    assert layout.template_brain == Path(
        f"resources/templates/tpl-{SPACE}_res-01_desc-brain_T1w.nii.gz"
    )
    assert layout.dataset_description == Path("results/dataset_description.json")
    assert layout.dseg_tsv == Path("results/dseg.tsv")
    assert layout.qc_index == Path("results/qc/index.html")


@pytest.mark.parametrize("step", ["metadata", "template", "describe", "qc_index"])
def test_dataset_step_logs_sit_directly_in_logs(step):
    assert paths.dataset_log_path(Path("logs"), step) == Path(f"logs/{step}.log")
