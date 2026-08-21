"""Test settings come from the test, never from the developer's `.env`.

`Settings` reads `.env`, and until now the suite inherited whatever the
person running it happened to have there. That was invisible for as long as
the file held only connection strings, because every developer's differed in
ways nothing asserted on.

Enabling `RBAC_ENABLED` locally made it visible: two tests in
`test_policy_set_policy_index_routes.py` began failing, not because anything
they cover had changed, but because they call administer-band operations —
index rebuild, project delete — with no credentials, and enforcement had
been switched on underneath them by a file they never mention.

That is the wrong direction of dependency. A suite that passes or fails on
an untracked file cannot be trusted to mean the same thing twice, and the
failure it produces points at the test rather than at the setting.

So the identity settings are pinned here for the whole session, before
`Settings` is ever constructed. `setdefault` is deliberately not used: the
point is to *override* the developer's file, not to defer to it.

Tests that need enforcement on turn it on themselves and clear the settings
cache — `test_rbac_authz.py` does exactly that — which is the arrangement
worth having. Enforcement is then something a test asks for explicitly, and
its absence elsewhere is a stated default rather than an accident of whose
machine it ran on.

Only the flags that change behaviour across the whole surface are pinned.
Database and AI settings are left alone: tests already manage those, and
widening this would quietly become a second configuration system.
"""
from __future__ import annotations

import os

import pytest

#: Pinned before any import that might construct `Settings`.
_PINNED = {
    "RBAC_ENABLED": "false",
    "DEV_AUTH_ENABLED": "true",
    "ENVIRONMENT": "development",
    "LOCAL_ACCOUNTS_ENABLED": "false",
    "TRUST_PLATFORM_AUTH_HEADER": "false",
    "ENTRA_ISSUER": "",
    "ENTRA_AUDIENCE": "",
    "ENTRA_JWKS_URL": "",
}

for _key, _value in _PINNED.items():
    os.environ[_key] = _value


@pytest.fixture(autouse=True)
def _identity_settings_are_the_tests_own():
    """Restore the pinned values after any test that changed them.

    A test that enables enforcement and forgets to undo it would otherwise
    hand its setting to everything that runs after it, and the failure would
    surface in an unrelated file — the most expensive kind to diagnose,
    because the evidence is nowhere near the cause.

    The settings cache is cleared on the way out for the same reason: a
    cached `Settings` outlives the environment variable it was built from.
    """

    yield

    for key, value in _PINNED.items():
        os.environ[key] = value

    try:
        from policy_platform.infrastructure.settings import get_settings

        get_settings.cache_clear()
    except Exception:  # noqa: BLE001 - a suite that cannot import settings has bigger problems
        pass
