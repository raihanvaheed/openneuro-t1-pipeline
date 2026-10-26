"""docs/fingerprints.txt lists the published SHA-256 of 91 files; check it against paths.py."""

import re
from pathlib import Path

import pytest

from openneuro_t1 import paths
from openneuro_t1.config import PROJECT_ROOT, load_config

FINGERPRINTS = PROJECT_ROOT / "docs" / "fingerprints.txt"
LINE = re.compile(r"[0-9a-f]{64}  \S+")

# 10 raw T1w scans, the template brain, and 8 NIfTI or matrix files for each of 10 subjects.
EXPECTED_LINES = 91


def listed() -> list[tuple[str, str]]:
    """(hash, path) for each line of the published list."""
    return [
        (line[:64], line[66:])
        for line in FINGERPRINTS.read_text(encoding="utf-8").splitlines()
    ]


def not_built_by_paths_py(listed_paths: list[str], built: set[str]) -> list[str]:
    return [path for path in listed_paths if path not in built]


@pytest.fixture
def built(tmp_path, monkeypatch) -> set[str]:
    """Every file the list may name, as paths.py builds them for the configured subjects.

    Built in an empty directory, so looking up a raw T1w cannot depend on whether
    resources/ exists on the machine running the tests.
    """
    monkeypatch.chdir(tmp_path)
    config = load_config()
    raw = Path(config["paths"]["raw"])
    results = Path(config["paths"]["results"])
    files = []
    for subject in config["subjects"]:
        layout = paths.subject_paths(
            subject, raw=raw, results=results, template=config["template"]
        )
        files += [
            layout.raw_t1w,
            layout.brain,
            layout.mask,
            layout.dseg,
            *layout.probseg.values(),
            layout.registered,
            layout.matrix,
        ]
    files.append(
        paths.dataset_paths(
            raw=raw,
            templates=Path(config["paths"]["templates"]),
            results=results,
            template=config["template"],
            resolution=config["template_resolution"],
        ).template_brain
    )
    return {file.as_posix() for file in files}


def test_the_list_has_91_lines():
    assert len(listed()) == EXPECTED_LINES


def test_each_line_is_a_hash_two_spaces_and_a_relative_path():
    for line in FINGERPRINTS.read_text(encoding="utf-8").splitlines():
        assert LINE.fullmatch(line), line
        path = Path(line[66:])
        assert not path.is_absolute() and ".." not in path.parts, line


def test_the_lines_are_in_c_locale_order():
    names = [path for _, path in listed()]
    assert names == sorted(names, key=lambda name: name.encode())


def test_every_listed_path_is_one_paths_py_builds(built):
    assert not_built_by_paths_py([path for _, path in listed()], built) == []


def test_paths_py_builds_exactly_the_files_listed(built):
    names = [path for _, path in listed()]
    assert len(set(names)) == len(names), "a path is listed twice"
    assert set(names) == built
    assert len(built) == EXPECTED_LINES


def test_a_path_that_drifts_from_paths_py_is_noticed(built):
    drifted = "results/sub-01/anat/sub-01_desc-brain_mask.nii"  # extension changed
    renamed = "results/sub-01/anat/sub-01_desc-mask_mask.nii.gz"
    assert not_built_by_paths_py([drifted, renamed], built) == [drifted, renamed]
