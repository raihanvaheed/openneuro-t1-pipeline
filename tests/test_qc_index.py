"""The QC index page, built from a small fake results tree."""

import json

import pytest

from openneuro_t1 import paths, qc_index

SPACE = "MNI152NLin2009cAsym"
IMAGE = {"tag": "brainlife/fsl:6.0.4-patched2", "digest": "sha256:abc", "image_id": "x"}


def fake_subject(tmp_path, subject, images=(IMAGE,)):
    layout = paths.subject_paths(
        subject, raw=tmp_path / "raw", results=tmp_path / "results", template=SPACE
    )
    for figure in (layout.skullstrip_png, layout.tissues_png, layout.registration_png):
        figure.parent.mkdir(parents=True, exist_ok=True)
        figure.write_bytes(b"png")
    layout.runinfo.parent.mkdir(parents=True, exist_ok=True)
    layout.runinfo.write_text(
        json.dumps(
            {
                "docker_images": list(images),
                "steps": {
                    step: {"seconds": 10.0 + number}
                    for number, step in enumerate(paths.FRAGMENT_STEPS)
                },
            }
        )
    )
    return layout


def build(tmp_path, subjects, **overrides):
    destination = paths.qc_index_path(tmp_path / "results")
    arguments = {
        "subjects": subjects,
        "dataset": "ds000102",
        "version": "0.1.0",
        "raw": tmp_path / "raw",
        "results": tmp_path / "results",
        "template": SPACE,
        "destination": destination,
    } | overrides
    qc_index.build_qc_index(**arguments)
    return destination


def test_images_are_linked_by_relative_path_not_embedded(tmp_path):
    for subject in ("01", "02"):
        fake_subject(tmp_path, subject)

    page = build(tmp_path, ["01", "02"]).read_text()

    assert 'href="../sub-01/figures/sub-01_desc-skullstrip_T1w.png"' in page
    assert 'src="../sub-02/figures/sub-02_desc-tissues_dseg.png"' in page
    assert f"../sub-02/figures/sub-02_space-{SPACE}_desc-registration_T1w.png" in page
    assert str(tmp_path) not in page
    assert "data:" not in page


def test_every_subject_is_listed_in_config_order_with_its_timings(tmp_path):
    for subject in ("03", "01", "02"):
        fake_subject(tmp_path, subject)

    page = build(tmp_path, ["03", "01", "02"]).read_text()

    headings = [f"<h3>sub-{s}</h3>" for s in ("03", "01", "02")]
    assert [page.index(h) for h in headings] == sorted(page.index(h) for h in headings)
    for step in paths.FRAGMENT_STEPS:
        assert f"<th>{step}</th>" in page
    assert (
        "<td>sub-01</td><td>10.0</td><td>11.0</td><td>12.0</td><td>13.0</td><td>14.0</td>"
        in page
    )


def test_the_header_names_the_version_dataset_and_image_digests(tmp_path):
    fake_subject(tmp_path, "01")

    page = build(tmp_path, ["01"]).read_text()

    assert "Pipeline version 0.1.0" in page
    assert "Dataset ds000102" in page
    assert "brainlife/fsl:6.0.4-patched2 sha256:abc" in page
    assert "this page makes no judgement on them" in page


def test_the_same_image_in_every_subject_is_listed_once(tmp_path):
    for subject in ("01", "02"):
        fake_subject(tmp_path, subject)

    page = build(tmp_path, ["01", "02"]).read_text()

    assert page.count("sha256:abc") == 1


def test_a_subject_with_a_missing_image_fails_the_step_and_is_named(tmp_path):
    fake_subject(tmp_path, "01")
    broken = fake_subject(tmp_path, "02")
    fake_subject(tmp_path, "03")
    broken.tissues_png.unlink()

    with pytest.raises(qc_index.QcIndexError) as error:
        build(tmp_path, ["01", "02", "03"])

    message = str(error.value)
    assert "sub-02" in message and "sub-02_desc-tissues_dseg.png" in message
    assert "sub-01" not in message and "sub-03" not in message
    assert not paths.qc_index_path(tmp_path / "results").exists()


def test_a_subject_without_runinfo_fails_the_step_and_is_named(tmp_path):
    fake_subject(tmp_path, "01").runinfo.unlink()

    with pytest.raises(qc_index.QcIndexError, match="sub-01_runinfo.json"):
        build(tmp_path, ["01"])


def test_a_subject_with_no_files_at_all_is_not_left_out_silently(tmp_path):
    fake_subject(tmp_path, "01")

    with pytest.raises(qc_index.QcIndexError, match="sub-02"):
        build(tmp_path, ["01", "02"])


def test_text_is_escaped(tmp_path):
    fake_subject(
        tmp_path,
        "01",
        images=({"tag": "x<img src=y>", "digest": "sha256:a&b", "image_id": "z"},),
    )

    page = build(tmp_path, ["01"], dataset='ds"<b>', version="<script>").read_text()

    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<b>" not in page and "ds&quot;&lt;b&gt;" in page
    assert "<img src=y>" not in page and "x&lt;img src=y&gt;" in page
    assert "sha256:a&amp;b" in page
