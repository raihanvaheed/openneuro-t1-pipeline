"""BET, FAST and FLIRT command lines, built by NiWrap's DryRunner (no Docker).

A dry run creates nothing, and it reports outputs as paths relative to the
working directory. Each test therefore runs in a temporary directory holding
stand-ins for what the tool would have written, so the real copy-out code runs.
"""

import nibabel as nib
import niwrap
import numpy as np
import pytest

from openneuro_t1 import anat

SHAPE = (3, 3, 3)  # 27 voxels: 9 CSF, 9 GM, 9 WM


def write_image(path, data):
    nib.save(nib.Nifti1Image(np.asarray(data, dtype="float32"), np.eye(4)), path)


def flag_values(cargs):
    return {
        arg: cargs[i + 1] for i, arg in enumerate(cargs[:-1]) if arg.startswith("-")
    }


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_segmentation(workdir, intensities):
    """A brain image and FAST-style outputs for it; intensities are CSF, GM, WM."""
    labels = np.repeat([1, 2, 3], 9).reshape(SHAPE)
    brain = workdir / "brain.nii.gz"
    write_image(brain, np.select([labels == i for i in (1, 2, 3)], intensities))
    write_image(workdir / "fast_seg.nii.gz", labels)
    for i in range(3):
        write_image(workdir / f"fast_pve_{i}.nii.gz", labels == i + 1)
    return brain


def test_skull_strip_asks_for_the_brain_mask_and_nothing_else(workdir):
    write_image(workdir / "img_bet.nii.gz", np.ones(SHAPE))
    write_image(workdir / "img_bet_mask.nii.gz", np.ones(SHAPE))
    t1w = workdir / "sub-01_T1w.nii.gz"
    brain = workdir / "out" / "brain.nii.gz"
    mask = workdir / "out" / "mask.nii.gz"
    dry = niwrap.DryRunner()

    anat.skull_strip(t1w, brain, mask, frac=0.5, runner=dry)

    assert dry.last_cargs[:3] == ["bet", str(t1w), "img_bet"]
    assert dry.last_cargs[3:] == ["-f", "0.5", "-m"]
    assert brain.exists() and mask.exists()


def test_segment_asks_for_three_classes_of_t1_type(workdir):
    brain = make_segmentation(workdir, intensities=(10, 20, 30))
    dseg = workdir / "out" / "dseg.nii.gz"
    probseg = {n: workdir / "out" / f"{n}.nii.gz" for n in anat.TISSUES}
    dry = niwrap.DryRunner()

    means = anat.segment(brain, dseg, probseg, classes=3, runner=dry)

    assert dry.last_cargs[0] == "fast"
    assert flag_values(dry.last_cargs) == {"-n": "3", "-t": "1", "-o": "fast"}
    assert dry.last_cargs[-1] == str(brain)
    assert dseg.exists() and all(p.exists() for p in probseg.values())
    assert means["dseg label"] == {"CSF": 10.0, "GM": 20.0, "WM": 30.0}
    assert means["partial-volume map"] == {"CSF": 10.0, "GM": 20.0, "WM": 30.0}


def test_segment_copies_pve_maps_in_csf_gm_wm_order(workdir):
    brain = make_segmentation(workdir, intensities=(10, 20, 30))
    probseg = {n: workdir / "out" / f"{n}.nii.gz" for n in anat.TISSUES}

    anat.segment(
        brain,
        workdir / "out" / "dseg.nii.gz",
        probseg,
        classes=3,
        runner=niwrap.DryRunner(),
    )

    for index, name in enumerate(anat.TISSUES):
        assert nib.load(probseg[name]).get_fdata().sum() == 9
        assert nib.load(probseg[name]).get_fdata().reshape(-1)[index * 9] == 1


@pytest.mark.parametrize("intensities", [(20, 10, 30), (10, 30, 20), (10, 10, 30)])
def test_segment_refuses_classes_that_do_not_rise_and_writes_nothing(
    workdir, intensities
):
    brain = make_segmentation(workdir, intensities=intensities)
    dseg = workdir / "out" / "dseg.nii.gz"
    probseg = {n: workdir / "out" / f"{n}.nii.gz" for n in anat.TISSUES}

    with pytest.raises(anat.ClassOrderError):
        anat.segment(brain, dseg, probseg, classes=3, runner=niwrap.DryRunner())

    assert not (workdir / "out").exists()


def test_segment_refuses_a_class_count_the_labels_do_not_cover(workdir):
    brain = make_segmentation(workdir, intensities=(10, 20, 30))
    with pytest.raises(ValueError):
        anat.segment(
            brain, workdir / "d.nii.gz", {}, classes=4, runner=niwrap.DryRunner()
        )


def test_register_uses_12_degrees_of_freedom_and_saves_the_matrix(workdir):
    write_image(workdir / anat.FLIRT_OUT_FILE, np.ones(SHAPE))
    (workdir / anat.FLIRT_OUT_MATRIX).write_text("1 0 0 0\n")
    brain = workdir / "brain.nii.gz"
    template = workdir / "template.nii.gz"
    registered = workdir / "out" / "registered.nii.gz"
    matrix = workdir / "out" / "xfm.mat"
    dry = niwrap.DryRunner()

    anat.register(brain, template, registered, matrix, dof=12, runner=dry)

    assert dry.last_cargs[0] == "flirt"
    flags = flag_values(dry.last_cargs)
    assert flags["-dof"] == "12"
    assert flags["-in"] == str(brain)
    assert flags["-ref"] == str(template)
    assert flags["-omat"] == anat.FLIRT_OUT_MATRIX
    assert flags["-out"] == anat.FLIRT_OUT_FILE
    assert "-cost" not in flags  # default cost function
    assert registered.exists() and matrix.read_text() == "1 0 0 0\n"


def test_dseg_tsv_has_index_and_name_columns(tmp_path):
    path = tmp_path / "dseg.tsv"
    anat.write_dseg_tsv(path)
    assert path.read_text() == "index\tname\n1\tCSF\n2\tGM\n3\tWM\n"


def test_container_images_come_from_niwrap_metadata():
    assert anat.container_images(["bet", "fast", "flirt"]) == [
        "brainlife/fsl:6.0.4-patched2"
    ]
    assert anat.container_images([]) == []
