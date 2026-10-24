"""The openneuro-t1 command line: --step parsing, scope errors, the full run's order."""

import pytest

from openneuro_t1 import run_subject

DATASET_STEPS = ["metadata", "template", "describe", "qc_index"]
SUBJECT_STEPS = ["fetch", "bet", "fast", "flirt", "qc", "runinfo"]


class Calls(list):
    """The (step, subject, force) of each run_step call; `ran` names the steps that run."""

    def __init__(self):
        super().__init__()
        self.ran = set()


@pytest.fixture
def calls(monkeypatch):
    """Record run_step calls instead of running anything."""
    recorded = Calls()

    def fake_run_step(name, config=None, subject=None, force=False):
        recorded.append((name, subject, force))
        return name in recorded.ran

    monkeypatch.setattr(run_subject, "run_step", fake_run_step)
    return recorded


def test_every_step_has_the_scope_of_the_prompts_table():
    scopes = {name: step.scope for name, step in run_subject.STEPS.items()}
    assert scopes == {
        **{name: "dataset" for name in DATASET_STEPS},
        **{name: "subject" for name in SUBJECT_STEPS},
    }


@pytest.mark.parametrize("step", SUBJECT_STEPS)
def test_a_subject_step_runs_for_the_given_subject(calls, step):
    assert run_subject.main(["--subject", "03", "--step", step]) == 0
    assert calls == [(step, "03", False)]


@pytest.mark.parametrize("step", DATASET_STEPS)
def test_a_dataset_step_runs_without_a_subject(calls, step):
    assert run_subject.main(["--step", step, "--force"]) == 0
    assert calls == [(step, None, True)]


@pytest.mark.parametrize("step", SUBJECT_STEPS)
def test_a_subject_step_without_a_subject_is_an_error(calls, capsys, step):
    with pytest.raises(SystemExit) as error:
        run_subject.main(["--step", step])
    assert error.value.code == 2
    assert "needs --subject" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize("step", DATASET_STEPS)
def test_a_dataset_step_with_a_subject_is_an_error(calls, capsys, step):
    with pytest.raises(SystemExit) as error:
        run_subject.main(["--subject", "01", "--step", step])
    assert error.value.code == 2
    assert "takes no --subject" in capsys.readouterr().err
    assert calls == []


def test_a_full_run_needs_a_subject(calls, capsys):
    with pytest.raises(SystemExit) as error:
        run_subject.main([])
    assert error.value.code == 2
    assert "--subject is required" in capsys.readouterr().err


def test_an_unknown_step_is_an_error(calls):
    with pytest.raises(SystemExit) as error:
        run_subject.main(["--subject", "01", "--step", "nonsense"])
    assert error.value.code == 2


def test_a_full_run_goes_through_the_steps_in_order_and_skips_qc_index(calls):
    run_subject.main(["--subject", "01"])

    assert [name for name, _, _ in calls] == [
        "metadata",
        "template",
        "fetch",
        "bet",
        "fast",
        "flirt",
        "qc",
        "describe",
        "runinfo",
    ]
    assert "qc_index" not in [name for name, _, _ in calls]
    for name, subject, _ in calls:
        expected = None if name in DATASET_STEPS else "01"
        assert subject == expected, name


def test_a_full_run_forces_every_step_only_when_asked(calls):
    run_subject.main(["--subject", "01"])
    assert not any(force for _, _, force in calls)

    calls.clear()
    run_subject.main(["--subject", "01", "--force"])
    assert all(force for _, _, force in calls)


def test_a_full_run_that_skips_everything_leaves_runinfo_alone(calls):
    run_subject.main(["--subject", "01"])
    assert ("runinfo", "01", False) in calls


@pytest.mark.parametrize("step", ["metadata", "bet", "qc", "describe"])
def test_a_full_run_that_ran_any_step_merges_runinfo_again(calls, step):
    calls.ran.add(step)
    run_subject.main(["--subject", "01"])
    assert ("runinfo", "01", True) in calls
