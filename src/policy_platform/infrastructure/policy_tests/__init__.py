"""Saved tests: proposing them, committing to them, and running them.

A policy test pins an expected decision to a set of facts, so a change that
would alter that decision is visible before it ships rather than after.

`ai_test_proposal` drafts candidate tests, which a human accepts or rejects --
an accepted test is a commitment the platform then holds itself to, which is
what `policy_test_commitment` records. `policy_test_execution` runs them
against stored versions.

The runner itself is not here. `evaluator/test_runner.py` is pure and takes an
in-memory package, so the same code decides a saved test, a live evaluation and
the on-publish re-run. This package is the database-aware half: it loads the
version, calls that runner, and writes the result to an append-only log.
"""
from __future__ import annotations
