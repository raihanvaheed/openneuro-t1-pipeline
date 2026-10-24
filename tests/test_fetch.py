from pathlib import Path

from openneuro_t1 import fetch

S3_URI = "s3://openneuro.org/ds000102"


def test_sync_is_anonymous_and_limited_to_the_subjects_t1w(tmp_path):
    command = fetch.sync_command("01", S3_URI, tmp_path)

    assert command[:4] == ["aws", "s3", "sync", "--no-sign-request"]
    assert command[4:6] == [f"{S3_URI}/", f"{tmp_path}/"]
    assert command[6:8] == ["--exclude", "*"]
    assert command.count("--include") == 3
    assert "sub-01/anat/*T1w.nii.gz" in command
    assert "--profile" not in command


def test_sync_adds_dataset_files_only_while_they_are_missing(tmp_path: Path):
    for name in fetch.DATASET_FILES:
        (tmp_path / name).touch()
    command = fetch.sync_command("01", S3_URI, tmp_path)
    assert command.count("--include") == 1

    (tmp_path / "participants.tsv").unlink()
    command = fetch.sync_command("01", S3_URI, tmp_path)
    assert command[-2:] == ["--include", "participants.tsv"]
