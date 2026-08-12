"""The mutation harness must never report a mutation it did not make.

A mutation run answers one question: was the code broken on purpose, and did
the suite notice? There is a failure mode that answers it wrongly and looks
identical to a real finding — the substitution matches nothing, the code stays
correct, the tests pass, and the run reports the mutation as surviving. That
reads as "the tests do not catch this", which is a confident wrong conclusion
about coverage, and it has already happened here: a shell one-liner with subtly
wrong quoting silently replaced nothing and the suite passed.

So the harness treats a missing target as an error, and these tests hold it to
that. Everything else it does is bookkeeping; this is the guarantee.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from mutation_check import (  # noqa: E402
    Mutation,
    TargetNotFound,
    _write,
    apply_mutation,
    check,
    main,
)


@pytest.fixture()
def sample(tmp_path: Path) -> Path:
    path = tmp_path / "subject.py"
    path.write_text("def forbids():\n    return True\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# A missing target is an error, never a silent pass
# --------------------------------------------------------------------------


def test_a_target_that_is_not_there_raises(sample: Path):
    """The whole reason this module exists."""

    with pytest.raises(TargetNotFound):
        apply_mutation(sample, "text that is not in the file", "anything")


def test_a_missing_target_leaves_the_file_untouched(sample: Path):
    before = sample.read_text(encoding="utf-8")

    with pytest.raises(TargetNotFound):
        apply_mutation(sample, "absent", "replacement")

    assert sample.read_text(encoding="utf-8") == before


def test_a_run_with_a_missing_target_fails_loudly(tmp_path: Path, capsys):
    """Exit status distinguishes it from both other outcomes.

    0 means every mutation was caught, 1 means one survived, and 2 means the
    run could not answer the question. Collapsing the third into either of the
    first two is how a broken check passes for a clean one.
    """

    target = tmp_path / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            [
                {
                    "name": "not present",
                    "file": str(target),
                    "find": "y = 2",
                    "replace": "y = 3",
                    "tests": ["tests/unit/test_mutation_check.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert main([str(spec)]) == 2
    assert "target not found" in capsys.readouterr().out.lower()


# --------------------------------------------------------------------------
# The file is always restored
# --------------------------------------------------------------------------


def test_a_crlf_file_matches_a_spec_written_with_newlines(tmp_path: Path):
    """Specs are written with `\\n`; a Windows checkout has `\\r\\n`.

    Without normalising, every multi-line mutation reported "target not found"
    on this platform — loud, but unusable.
    """

    path = tmp_path / "crlf.py"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("def f():\r\n    return True\r\n")

    original, newline = apply_mutation(path, "def f():\n    return True", "def f():\n    return False")

    assert newline == "\r\n"
    with path.open("r", encoding="utf-8", newline="") as handle:
        assert handle.read() == "def f():\r\n    return False\r\n"

    _write(path, original, newline)
    with path.open("r", encoding="utf-8", newline="") as handle:
        assert handle.read() == "def f():\r\n    return True\r\n"


def test_the_file_is_restored_after_a_mutation(sample: Path, monkeypatch):
    """A mutation run must not leave the working tree modified."""

    before = sample.read_text(encoding="utf-8")
    monkeypatch.setattr("mutation_check.run_tests", lambda tests: True)

    check(
        Mutation(
            name="m",
            file=sample,
            find="return True",
            replace="return False",
            tests=("tests/unit/test_mutation_check.py",),
        )
    )

    assert sample.read_text(encoding="utf-8") == before


def test_the_file_is_restored_even_when_the_run_raises(sample: Path, monkeypatch):
    before = sample.read_text(encoding="utf-8")

    def explode(tests):
        raise RuntimeError("pytest could not start")

    monkeypatch.setattr("mutation_check.run_tests", explode)

    with pytest.raises(RuntimeError):
        check(
            Mutation(
                name="m",
                file=sample,
                find="return True",
                replace="return False",
                tests=("tests/unit/test_mutation_check.py",),
            )
        )

    assert sample.read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------
# Survival is reported the right way round
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "suite_passed,expected_survived",
    [(True, True), (False, False)],
)
def test_a_passing_suite_means_the_mutation_survived(
    sample: Path, monkeypatch, suite_passed: bool, expected_survived: bool
):
    """Easy to invert, and inverting it reverses every conclusion.

    The code is broken on purpose. A suite that still passes did not notice —
    that is survival, and it is the finding worth acting on.
    """

    monkeypatch.setattr("mutation_check.run_tests", lambda tests: suite_passed)

    survived = check(
        Mutation(
            name="m",
            file=sample,
            find="return True",
            replace="return False",
            tests=("tests/unit/test_mutation_check.py",),
        )
    )

    assert survived is expected_survived


# --------------------------------------------------------------------------
# The spec has to say enough to be worth running
# --------------------------------------------------------------------------


def test_a_mutation_naming_no_tests_is_rejected():
    """Running the whole suite for every mutation is slow enough to discourage
    the practice, and narrow enough selections are what make it usable."""

    with pytest.raises(ValueError, match="names no tests"):
        Mutation.from_spec({"file": "a.py", "find": "x", "replace": "y"}, 0)


@pytest.mark.parametrize("missing", ["file", "find", "replace"])
def test_an_incomplete_mutation_is_rejected(missing: str):
    spec = {"file": "a.py", "find": "x", "replace": "y", "tests": ["t"]}
    spec.pop(missing)

    with pytest.raises(ValueError, match=missing):
        Mutation.from_spec(spec, 0)
