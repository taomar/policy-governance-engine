"""Tests for the role vocabulary and privilege ordering in api/roles.py."""
from __future__ import annotations

from policy_platform.api.roles import (
    ADMIN,
    ADMINISTER,
    AUTHOR,
    BAND_MINIMUM_ROLE,
    POLICY_AUTHOR,
    READ,
    USE,
    VIEWER,
    role_satisfies,
)


# ── role_satisfies ordering ──────────────────────────────────────────


def test_viewer_satisfies_viewer():
    assert role_satisfies(VIEWER, minimum=VIEWER)


def test_policy_author_satisfies_viewer():
    assert role_satisfies(POLICY_AUTHOR, minimum=VIEWER)


def test_admin_satisfies_all_roles():
    for role in (VIEWER, POLICY_AUTHOR, ADMIN):
        assert role_satisfies(ADMIN, minimum=role)


def test_viewer_does_not_satisfy_policy_author():
    assert not role_satisfies(VIEWER, minimum=POLICY_AUTHOR)


def test_viewer_does_not_satisfy_admin():
    assert not role_satisfies(VIEWER, minimum=ADMIN)


def test_policy_author_does_not_satisfy_admin():
    assert not role_satisfies(POLICY_AUTHOR, minimum=ADMIN)


def test_unknown_role_satisfies_nothing():
    """Default closed: an unrecognised role must not gain any access."""
    assert not role_satisfies("superuser", minimum=VIEWER)
    assert not role_satisfies("", minimum=VIEWER)


def test_unknown_minimum_is_never_satisfied():
    """An unknown minimum cannot be met, even by admin."""
    assert not role_satisfies(ADMIN, minimum="overlord")


# ── band definitions ─────────────────────────────────────────────────


def test_every_band_has_a_minimum_role():
    for band in (READ, USE, AUTHOR, ADMINISTER):
        assert band in BAND_MINIMUM_ROLE


def test_read_and_use_require_viewer():
    assert BAND_MINIMUM_ROLE[READ] == VIEWER
    assert BAND_MINIMUM_ROLE[USE] == VIEWER


def test_author_requires_policy_author():
    assert BAND_MINIMUM_ROLE[AUTHOR] == POLICY_AUTHOR


def test_administer_requires_admin():
    assert BAND_MINIMUM_ROLE[ADMINISTER] == ADMIN
