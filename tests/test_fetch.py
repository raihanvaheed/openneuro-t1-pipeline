import pytest

from openneuro_t1 import fetch

S3_URI = "s3://openneuro.org/ds000102"


def fake_sync(tmp_path, seen, creates=()):
    """A stand-in for fetch._sync that records the include patterns."""

    def sync(config, includes):
        seen.append(includes)
        for relative in creates:
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).touch()
        return tmp_path

    return sync


def test_sync_is_anonymous_and_limited_to_the_given_patterns(tmp_path):
    command = fetch.sync_command(
        S3_URI, tmp_path, ["a.json", "sub-01/anat/*T1w.nii.gz"]
    )

    assert command[:4] == ["aws", "s3", "sync", "--no-sign-request"]
    assert command[4:6] == [f"{S3_URI}/", f"{tmp_path}/"]
    assert command[6:8] == ["--exclude", "*"]
    assert command[8:] == [
        "--include",
        "a.json",
        "--include",
        "sub-01/anat/*T1w.nii.gz",
    ]
    assert "--profile" not in command


def test_fetch_subject_fetches_only_that_subjects_t1w(tmp_path, monkeypatch):
    seen = []
    t1w = "sub-04/anat/sub-04_T1w.nii.gz"
    monkeypatch.setattr(fetch, "_sync", fake_sync(tmp_path, seen, [t1w]))

    result = fetch.fetch_subject("04", {})

    assert seen == [["sub-04/anat/*T1w.nii.gz"]]
    assert result == tmp_path / t1w


def test_fetch_subject_fails_when_no_t1w_arrives(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_sync", fake_sync(tmp_path, []))
    with pytest.raises(FileNotFoundError):
        fetch.fetch_subject("04", {})


def test_fetch_metadata_fetches_only_the_two_dataset_files(tmp_path, monkeypatch):
    seen = []
    names = ["dataset_description.json", "participants.tsv"]
    monkeypatch.setattr(fetch, "_sync", fake_sync(tmp_path, seen, names))

    result = fetch.fetch_metadata({"paths": {"raw": str(tmp_path)}})

    assert seen == [names]
    assert result == [tmp_path / name for name in names]


def test_fetch_metadata_fails_when_a_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fetch, "_sync", fake_sync(tmp_path, [], ["dataset_description.json"])
    )
    with pytest.raises(FileNotFoundError, match="participants.tsv"):
        fetch.fetch_metadata({"paths": {"raw": str(tmp_path)}})
