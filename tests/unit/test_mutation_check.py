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
    ConcurrentRun,
    FileUnavailable,
    Mutation,
    RestoreFailed,
    TargetNotFound,
    _write,
    apply_mutation,
    check,
    exclusive_lock,
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


def test_a_failed_write_leaves_the_original_intact(sample: Path, monkeypatch):
    """The worst thing this tool could do is destroy a source file.

    The write goes to a temporary sibling and is moved into place, so a failure
    part-way through leaves the original untouched. The naive version opened
    the target directly, and a failure at that moment — observed on Windows,
    with the API running from the same checkout — would have truncated a source
    file outside any restore block.
    """

    import mutation_check

    before = sample.read_text(encoding="utf-8")

    def refuse(self, *args, **kwargs):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(mutation_check.Path, "open", refuse)

    with pytest.raises(OSError):
        mutation_check._write(sample, "replacement body", "\n")

    monkeypatch.undo()
    assert sample.read_text(encoding="utf-8") == before


def test_no_temporary_file_is_left_behind(sample: Path):
    mutation_check_tmp = sample.with_suffix(sample.suffix + ".mutation-tmp")

    import mutation_check

    mutation_check._write(sample, "def forbids():\n    return False\n", "\n")

    assert not mutation_check_tmp.exists()
    assert "return False" in sample.read_text(encoding="utf-8")


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


# --------------------------------------------------------------------------
# Two runs must not mutate one checkout at the same time
# --------------------------------------------------------------------------


@pytest.fixture()
def lock_in_tmp(tmp_path: Path, monkeypatch) -> Path:
    """Point the lock at a temporary directory, never the real checkout."""

    import mutation_check

    path = tmp_path / ".mutation-check.lock"
    monkeypatch.setattr(mutation_check, "LOCK_PATH", path)
    return path


def test_a_second_run_cannot_start_while_the_first_holds_the_lock(lock_in_tmp: Path):
    """The defect this closes was observed, not imagined.

    Two agents ran specs against one worktree at the same time. The harness
    reads the original, writes a mutation, and restores — so the second run can
    read the first run's mutation as its "original" and write that defect into
    source permanently, while both runs report success.
    """

    with exclusive_lock():
        assert lock_in_tmp.exists()
        with pytest.raises(ConcurrentRun, match="Another mutation run"):
            with exclusive_lock():
                pass


def test_the_lock_is_released_even_when_the_run_raises(lock_in_tmp: Path):
    """A lock that outlives its run would block every later run."""

    with pytest.raises(RuntimeError):
        with exclusive_lock():
            raise RuntimeError("suite could not start")

    assert not lock_in_tmp.exists()


def test_the_lock_records_who_holds_it(lock_in_tmp: Path):
    """A stale lock is reported, not broken, so it has to be diagnosable."""

    import os

    with exclusive_lock():
        held = lock_in_tmp.read_text(encoding="utf-8")

    assert f"pid={os.getpid()}" in held
    assert "started=" in held


def test_a_held_lock_makes_a_run_exit_three(tmp_path: Path, lock_in_tmp: Path, capsys):
    """Distinct from 1 (survived) and 2 (stale spec): nothing was measured."""

    target = tmp_path / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            [
                {
                    "name": "blocked",
                    "file": str(target),
                    "find": "x = 1",
                    "replace": "x = 2",
                    "tests": ["tests/unit/test_mutation_check.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    lock_in_tmp.write_text("pid=999999 started=earlier\n", encoding="utf-8")

    assert main([str(spec)]) == 3
    assert "another mutation run" in capsys.readouterr().out.lower()
    assert target.read_text(encoding="utf-8") == "x = 1\n"


# --------------------------------------------------------------------------
# A restore that did not restore is the loudest failure there is
# --------------------------------------------------------------------------


def test_a_restore_that_does_not_reproduce_the_original_raises(
    sample: Path, lock_in_tmp: Path, monkeypatch
):
    """Writing the original back is not the same as the original being back.

    Simulated by corrupting the file during the restore, which is what an
    interleaved second run does in practice.
    """

    import mutation_check

    monkeypatch.setattr("mutation_check.run_tests", lambda tests: True)

    real_write = mutation_check._write

    def write_something_else(path, text, newline):
        real_write(path, text + "# an edit nobody made\n", newline)

    monkeypatch.setattr("mutation_check._write", write_something_else)

    with pytest.raises(RestoreFailed, match="nobody wrote deliberately"):
        check(
            Mutation(
                name="m",
                file=sample,
                find="return True",
                replace="return False",
                tests=("tests/unit/test_mutation_check.py",),
            )
        )


def test_a_failed_restore_makes_a_run_exit_four(tmp_path: Path, lock_in_tmp: Path, monkeypatch, capsys):
    import mutation_check

    target = tmp_path / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            [
                {
                    "name": "corrupted",
                    "file": str(target),
                    "find": "x = 1",
                    "replace": "x = 2",
                    "tests": ["tests/unit/test_mutation_check.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("mutation_check.run_tests", lambda tests: False)
    real_write = mutation_check._write

    def write_something_else(path, text, newline):
        real_write(path, text + "# an edit nobody made\n", newline)

    monkeypatch.setattr("mutation_check._write", write_something_else)

    assert main([str(spec)]) == 4
    assert "restore failed" in capsys.readouterr().out.lower()


def test_a_clean_run_leaves_no_lock_behind(sample: Path, lock_in_tmp: Path, monkeypatch):
    """Otherwise the first successful run blocks every one after it."""

    monkeypatch.setattr("mutation_check.run_tests", lambda tests: False)

    spec = sample.parent / "spec.json"
    spec.write_text(
        json.dumps(
            [
                {
                    "name": "ordinary",
                    "file": str(sample),
                    "find": "return True",
                    "replace": "return False",
                    "tests": ["tests/unit/test_mutation_check.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert main([str(spec)]) == 0
    assert not lock_in_tmp.exists()


# --------------------------------------------------------------------------
# A file that cannot be written is not a finding about coverage
# --------------------------------------------------------------------------


def test_a_refused_rename_is_retried_before_giving_up(sample: Path, monkeypatch):
    """The lock behind it clears in milliseconds, so one attempt is too few.

    Observed on Windows with no server running from the checkout: `os.replace`
    returned `Access is denied` partway through a gate, on different files and
    different specs, because a rename fails while any handle is open and a
    scanner or an exiting test process holds one briefly.
    """

    import mutation_check

    attempts = {"count": 0}
    real_replace = mutation_check.os.replace

    def refuse_twice(source, destination):
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise PermissionError(5, "Access is denied")
        return real_replace(source, destination)

    monkeypatch.setattr(mutation_check.os, "replace", refuse_twice)
    monkeypatch.setattr(mutation_check, "_REPLACE_BACKOFF_SECONDS", 0)

    mutation_check._write(sample, "def forbids():\n    return False\n", "\n")

    assert attempts["count"] == 3
    assert "return False" in sample.read_text(encoding="utf-8")


def test_a_permanently_refused_rename_raises_rather_than_reporting_a_result(
    sample: Path, monkeypatch
):
    import mutation_check

    def always_refuse(source, destination):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(mutation_check.os, "replace", always_refuse)
    monkeypatch.setattr(mutation_check, "_REPLACE_BACKOFF_SECONDS", 0)

    with pytest.raises(FileUnavailable, match="Nothing was measured"):
        mutation_check._write(sample, "anything", "\n")


def test_a_refused_rename_leaves_no_temporary_file(sample: Path, monkeypatch):
    import mutation_check

    monkeypatch.setattr(
        mutation_check.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError(5, "denied"))
    )
    monkeypatch.setattr(mutation_check, "_REPLACE_BACKOFF_SECONDS", 0)

    with pytest.raises(FileUnavailable):
        mutation_check._write(sample, "anything", "\n")

    assert not sample.with_suffix(sample.suffix + ".mutation-tmp").exists()


def test_a_write_failure_makes_a_run_exit_five(tmp_path: Path, lock_in_tmp: Path, monkeypatch, capsys):
    """Five, not one.

    Exit 1 means the code was broken and the suite still passed — a finding
    about coverage. An environment that would not let a file be written is not
    that, and reporting it as that is how a bad run gets read as a bad test
    suite. This exact conflation happened: a PermissionError crashed the run
    with a traceback and exited 1, and the summary line was indistinguishable
    from two surviving mutations.
    """

    import mutation_check

    target = tmp_path / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            [
                {
                    "name": "unwritable",
                    "file": str(target),
                    "find": "x = 1",
                    "replace": "x = 2",
                    "tests": ["tests/unit/test_mutation_check.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mutation_check.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError(5, "denied"))
    )
    monkeypatch.setattr(mutation_check, "_REPLACE_BACKOFF_SECONDS", 0)

    assert main([str(spec)]) == 5
    assert "could not write" in capsys.readouterr().out.lower()
    assert target.read_text(encoding="utf-8") == "x = 1\n"
