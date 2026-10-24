import json
import tomllib
from datetime import UTC, datetime

from openneuro_t1 import provenance
from openneuro_t1.config import PROJECT_ROOT

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


def test_runinfo_records_versions_images_and_seconds_per_step(tmp_path):
    destination = tmp_path / "provenance" / "sub-01_runinfo.json"
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
    steps = {
        "bet": {"status": "ran", "seconds": 12.5},
        "fast": {"status": "skipped", "seconds": None},
    }
    images = [
        {"tag": "brainlife/fsl:x", "digest": "sha256:abc", "image_id": "sha256:def"}
    ]

    provenance.write_runinfo(destination, "01", started, finished, steps, images)

    info = json.loads(destination.read_text())
    assert info["subject"] == "01"
    assert info["started"] == "2026-01-01T12:00:00+00:00"
    assert info["finished"] == "2026-01-01T12:05:00+00:00"
    assert set(info["packages"]) == {"niwrap", "nilearn", "nibabel", "templateflow"}
    assert info["packages"]["niwrap"] == "1.1.0"
    assert info["python"].startswith("3.")
    assert info["docker_images"] == images
    assert info["steps"] == steps
