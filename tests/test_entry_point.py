from importlib.metadata import entry_points

from openneuro_t1 import run_subject


def test_openneuro_t1_command_resolves_to_the_run_subject_main():
    (entry_point,) = entry_points(group="console_scripts", name="openneuro-t1")

    assert entry_point.value == "openneuro_t1.run_subject:main"
    assert entry_point.load() is run_subject.main
