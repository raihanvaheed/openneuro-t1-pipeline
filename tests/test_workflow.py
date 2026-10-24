"""The Snakemake workflow names no file itself: every path comes from openneuro_t1.paths."""

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / "workflow"
REPORT = WORKFLOW / "report"

STRING_LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
HAND_BUILT = ("sub-", ".nii", ".png", ".json", ".mat")
RULE = re.compile(r"^rule (\w+):\n((?:[ \t]+.*\n|\n)*)", re.MULTILINE)


def hand_built_names(text: str) -> list[str]:
    """String literals that look like a hand-built filename."""
    return [
        literal
        for literal in STRING_LITERAL.findall(text)
        if any(marker in literal for marker in HAND_BUILT)
    ]


def workflow_files() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOW.rglob("*")
        if path.is_file() and REPORT not in path.parents
    )


def rules() -> dict[str, str]:
    found = {}
    for path in WORKFLOW.rglob("*.smk"):
        found.update({m.group(1): m.group(2) for m in RULE.finditer(path.read_text())})
    return found


@pytest.mark.parametrize(
    "text",
    [
        'output: "results/sub-01/anat/x.txt"',
        "output: 'brain.nii.gz'",
        'log: "logs/bet.json"',
        'input: "x.png"',
        'output: "transform.mat"',
    ],
)
def test_the_scan_finds_hand_built_filenames(text):
    assert hand_built_names(text) != []


def test_the_scan_leaves_commands_and_options_alone():
    text = (
        'configfile: "config/config.yaml"\n'
        'shell: "openneuro-t1 --subject {wildcards.subject} --step bet --force"\n'
        'subcategory="Subject {subject}"\n'
    )
    assert hand_built_names(text) == []


def test_the_workflow_files_exist():
    names = {path.relative_to(WORKFLOW).as_posix() for path in workflow_files()}
    assert {
        "Snakefile",
        "rules/common.smk",
        "rules/dataset.smk",
        "rules/subject.smk",
        "profiles/default/config.yaml",
    } <= names


@pytest.mark.parametrize("path", workflow_files(), ids=lambda p: p.name)
def test_no_workflow_file_builds_a_filename_by_hand(path):
    assert hand_built_names(path.read_text()) == []


def test_every_report_caption_the_rules_use_exists():
    for caption in re.findall(
        r'caption="([^"]+)"', (WORKFLOW / "rules/subject.smk").read_text()
    ):
        assert (WORKFLOW / "rules" / caption).resolve().exists(), caption


def test_the_rules_are_the_ten_steps_plus_all():
    snakefile = (WORKFLOW / "Snakefile").read_text()
    assert set(rules()) == {
        "metadata",
        "template",
        "describe",
        "qc_index",
        "fetch",
        "bet",
        "fast",
        "flirt",
        "qc",
        "runinfo",
    }
    assert "rule all:" in snakefile


@pytest.mark.parametrize("name", sorted(rules()))
def test_each_rule_runs_one_openneuro_t1_step_with_a_log_and_memory(name):
    body = rules()[name]

    assert re.search(rf'shell:\n\s+"openneuro-t1 [^"]*--step {name} --force"', body)
    assert "log:" in body
    assert re.search(r"resources:\n\s+mem_mb=memory\(", body)
    for forbidden in ("run:", "conda:", "container:", "singularity:"):
        assert forbidden not in body
