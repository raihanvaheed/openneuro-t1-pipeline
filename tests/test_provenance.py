import json
import tomllib
from datetime import UTC, datetime

import pytest

from openneuro_t1 import provenance
from openneuro_t1.config import PROJECT_ROOT
from openneuro_t1.paths import FRAGMENT_STEPS

S3_URI = "s3://openneuro.org/ds000102"


def write_raw_description(tmp_path, **extra):
    raw = tmp_path / "raw_dataset_description.json"
    raw.write_text(json.dumps({"Name": "Flanker", "License": "PDDL", **extra}))
    return raw


def test_dataset_description_declares_a_derivatives_dataset(tmp_path):
    destination = tmp_path / "dataset_description.json"
    provenance.write_dataset_description(
        destination, S3_URI, write_raw_description(tmp_path)
    )

    description = json.loads(destination.read_text())
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert description == {
        "Name": "openneuro-t1-pipeline derivatives",
        "BIDSVersion": "1.10.0",
        "DatasetType": "derivative",
        "GeneratedBy": [{"Name": "openneuro-t1-pipeline", "Version": version}],
        "SourceDatasets": [{"URL": S3_URI}],
    }


def test_dataset_description_carries_the_raw_doi_when_there_is_one(tmp_path):
    destination = tmp_path / "dataset_description.json"
    raw = write_raw_description(tmp_path, DOI="10.0000/example")
    provenance.write_dataset_description(destination, S3_URI, raw)

    source = json.loads(destination.read_text())["SourceDatasets"][0]
    assert source == {"URL": S3_URI, "DOI": "10.0000/example"}


IMAGE = {"tag": "brainlife/fsl:x", "digest": "sha256:abc", "image_id": "sha256:def"}
OTHER_IMAGE = {"tag": "other:y", "digest": "sha256:123", "image_id": "sha256:456"}


def at(minute, second=0):
    return datetime(2026, 1, 1, 12, minute, second, tzinfo=UTC)


def write_fragments(tmp_path, images=None):
    """Five fragments, one per step, written by the real writer."""
    images = images or {}
    paths = {}
    for number, step in enumerate(FRAGMENT_STEPS):
        paths[step] = tmp_path / "sub-01" / f"{step}.json"
        provenance.write_fragment(
            paths[step],
            "01",
            step,
            at(number),
            at(number, 30),
            10.0 + number,
            images.get(step, []),
        )
    return paths


def load_fragments(paths):
    return {step: json.loads(path.read_text()) for step, path in paths.items()}


def test_fragment_records_one_step_with_versions_and_images(tmp_path):
    destination = tmp_path / "sub-01" / "bet.json"

    provenance.write_fragment(destination, "01", "bet", at(0), at(1), 12.5, [IMAGE])

    fragment = json.loads(destination.read_text())
    assert fragment["subject"] == "01"
    assert fragment["step"] == "bet"
    assert fragment["started"] == "2026-01-01T12:00:00+00:00"
    assert fragment["finished"] == "2026-01-01T12:01:00+00:00"
    assert fragment["seconds"] == 12.5
    assert fragment["python"].startswith("3.")
    assert set(fragment["packages"]) == {
        "niwrap",
        "nilearn",
        "nibabel",
        "templateflow",
        "snakemake",
    }
    assert fragment["packages"]["niwrap"] == "1.1.0"
    assert "docker_default_platform" in fragment
    assert fragment["docker_images"] == [IMAGE]


def test_fragment_of_a_step_without_docker_lists_no_images(tmp_path):
    destination = tmp_path / "fetch.json"
    provenance.write_fragment(destination, "01", "fetch", at(0), at(1), 5.0, [])
    assert json.loads(destination.read_text())["docker_images"] == []


def test_merge_combines_the_fragments_into_one_record(tmp_path):
    images = {"bet": [IMAGE], "fast": [IMAGE], "flirt": [IMAGE, OTHER_IMAGE]}
    fragments = load_fragments(write_fragments(tmp_path, images))

    merged = provenance.merge_fragments("01", fragments)

    assert merged["subject"] == "01"
    assert merged["started"] == "2026-01-01T12:00:00+00:00"  # the earliest
    assert merged["finished"] == "2026-01-01T12:04:30+00:00"  # the latest
    assert merged["python"] == fragments["bet"]["python"]
    assert merged["packages"] == fragments["bet"]["packages"]
    assert (
        merged["docker_default_platform"] is fragments["bet"]["docker_default_platform"]
    )
    assert merged["docker_images"] == [IMAGE, OTHER_IMAGE]  # deduplicated by digest
    assert list(merged["steps"]) == list(FRAGMENT_STEPS)
    assert merged["steps"]["fast"] == {
        "started": "2026-01-01T12:02:00+00:00",
        "finished": "2026-01-01T12:02:30+00:00",
        "seconds": 12.0,
    }


@pytest.mark.parametrize(
    ("field", "other"),
    [
        ("python", "3.99.0"),
        ("packages", {"niwrap": "9.9.9"}),
        ("docker_default_platform", "linux/amd64"),
    ],
)
def test_merge_stops_and_names_the_steps_that_disagree(tmp_path, field, other):
    fragments = load_fragments(write_fragments(tmp_path))
    fragments["flirt"][field] = other

    with pytest.raises(provenance.ProvenanceError) as error:
        provenance.merge_fragments("01", fragments)

    assert field in str(error.value)
    assert "flirt" in str(error.value)
    assert "sub-01" in str(error.value)


def test_write_runinfo_merges_the_fragment_files(tmp_path):
    fragment_paths = write_fragments(tmp_path, {"bet": [IMAGE]})
    destination = tmp_path / "provenance" / "sub-01_runinfo.json"

    provenance.write_runinfo(destination, "01", fragment_paths)

    info = json.loads(destination.read_text())
    assert info["subject"] == "01"
    assert info["docker_images"] == [IMAGE]
    assert list(info["steps"]) == list(FRAGMENT_STEPS)


def test_write_runinfo_names_the_fragments_that_are_missing(tmp_path):
    fragment_paths = write_fragments(tmp_path)
    fragment_paths["fast"].unlink()
    fragment_paths["qc"].unlink()
    destination = tmp_path / "sub-01_runinfo.json"

    with pytest.raises(provenance.ProvenanceError, match="fast, qc"):
        provenance.write_runinfo(destination, "01", fragment_paths)
    assert not destination.exists()
