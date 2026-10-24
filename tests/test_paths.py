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
