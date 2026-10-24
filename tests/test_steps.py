"""run_step: the skip rule, provenance fragments as outputs, and per-step logs."""

import dataclasses
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from openneuro_t1 import paths, provenance, run_subject


@pytest.fixture
def config(tmp_path):
    return {
        "dataset": "ds000102",
        "s3_uri": "s3://example/ds000102",
        "subjects": ["01"],
        "template": "MNI152NLin2009cAsym",
        "template_resolution": 1,
        "paths": {
            name: str(tmp_path / name)
            for name in ("raw", "templateflow", "templates", "results", "logs")
        },
        "bet": {"frac": 0.5},
        "fast": {"classes": 3},
        "flirt": {"dof": 12},
    }


@pytest.fixture
def layout(tmp_path):
    return paths.subject_paths(
        "01",
        raw=tmp_path / "raw",
        results=tmp_path / "results",
        template="MNI152NLin2009cAsym",
    )


def fake_qc(monkeypatch, actions, tools=()):
    """Replace the qc step's work with one that writes its three figures."""

    def action(ctx):
        actions.append(ctx.subject)
        for figure in (
            ctx.layout.skullstrip_png,
            ctx.layout.tissues_png,
            ctx.layout.registration_png,
        ):
            figure.parent.mkdir(parents=True, exist_ok=True)
            figure.write_bytes(b"png")

    step = dataclasses.replace(run_subject.STEPS["qc"], action=action, tools=tools)
    monkeypatch.setitem(run_subject.STEPS, "qc", step)


def test_a_step_that_runs_writes_its_fragment_and_its_log(
    config, layout, monkeypatch, tmp_path
):
    actions = []
    fake_qc(monkeypatch, actions)

    assert run_subject.run_step("qc", config, "01") is True

    assert actions == ["01"]
    fragment = json.loads(layout.fragments["qc"].read_text())
    assert (fragment["subject"], fragment["step"]) == ("01", "qc")
    assert fragment["docker_images"] == []
    assert paths.log_path(tmp_path / "logs", "01", "qc").exists()


def test_a_finished_step_is_skipped_and_keeps_its_fragment(config, layout, monkeypatch):
    actions = []
    fake_qc(monkeypatch, actions)
    run_subject.run_step("qc", config, "01")
    before = layout.fragments["qc"].read_bytes()

    assert run_subject.run_step("qc", config, "01") is False

    assert actions == ["01"]  # not run a second time
    assert layout.fragments["qc"].read_bytes() == before


def test_a_step_whose_fragment_is_missing_is_not_finished(config, layout, monkeypatch):
    actions = []
    fake_qc(monkeypatch, actions)
    run_subject.run_step("qc", config, "01")
    layout.fragments["qc"].unlink()  # every figure is still there

    assert run_subject.run_step("qc", config, "01") is True

    assert actions == ["01", "01"]
    assert layout.fragments["qc"].exists()


def test_force_reruns_a_finished_step_and_rewrites_its_fragment(
    config, layout, monkeypatch
):
    actions = []
    fake_qc(monkeypatch, actions)
    run_subject.run_step("qc", config, "01")
    first = json.loads(layout.fragments["qc"].read_text())["finished"]

    assert run_subject.run_step("qc", config, "01", force=True) is True

    assert actions == ["01", "01"]
    assert json.loads(layout.fragments["qc"].read_text())["finished"] >= first


def test_a_failed_step_writes_no_fragment(config, layout, monkeypatch):
    def failing(ctx):
        raise RuntimeError("tool failed")

    step = dataclasses.replace(run_subject.STEPS["qc"], action=failing)
    monkeypatch.setitem(run_subject.STEPS, "qc", step)

    with pytest.raises(RuntimeError):
        run_subject.run_step("qc", config, "01")

    assert not layout.fragments["qc"].exists()


def test_a_docker_step_records_its_image_in_its_fragment(config, layout, monkeypatch):
    fake_qc(monkeypatch, [], tools=("bet",))
    monkeypatch.setattr(
        run_subject.anat,
        "use_docker_runner",
        lambda data_dir: SimpleNamespace(logger_name="styx_test_runner"),
    )
    monkeypatch.setattr(
        provenance,
        "inspect_images",
        lambda tags: [
            {"tag": t, "digest": "sha256:a", "image_id": "sha256:b"} for t in tags
        ],
    )

    run_subject.run_step("qc", config, "01")

    images = json.loads(layout.fragments["qc"].read_text())["docker_images"]
    assert [image["tag"] for image in images] == ["brainlife/fsl:6.0.4-patched2"]


def test_a_dataset_step_writes_no_fragment_and_logs_directly_in_logs(config, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "dataset_description.json").write_text('{"Name": "x"}')

    assert run_subject.run_step("describe", config) is True

    assert (tmp_path / "results" / "dataset_description.json").exists()
    assert (tmp_path / "results" / "dseg.tsv").exists()
    assert (tmp_path / "logs" / "describe.log").exists()
    assert not (tmp_path / "results" / "provenance").exists()


def write_fragments(layout):
    now = datetime.now(UTC)
    for step, path in layout.fragments.items():
        provenance.write_fragment(path, "01", step, now, now, 1.0, [])


def test_the_runinfo_step_merges_and_a_skipped_run_leaves_it_untouched(config, layout):
    write_fragments(layout)

    assert run_subject.run_step("runinfo", config, "01") is True
    merged = layout.runinfo.read_bytes()
    assert json.loads(merged)["subject"] == "01"

    assert run_subject.run_step("runinfo", config, "01") is False
    assert layout.runinfo.read_bytes() == merged


def test_the_runinfo_step_stops_when_fragments_disagree(config, layout):
    write_fragments(layout)
    flirt = json.loads(layout.fragments["flirt"].read_text())
    flirt["python"] = "3.99.0"
    layout.fragments["flirt"].write_text(json.dumps(flirt))

    with pytest.raises(provenance.ProvenanceError, match="flirt"):
        run_subject.run_step("runinfo", config, "01")

    assert not layout.runinfo.exists()
