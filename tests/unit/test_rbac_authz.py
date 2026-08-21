"""Tests for the RBAC enforcement layer in api/authz.py.

These tests flip ``rbac_enabled`` ON and prove enforcement genuinely
works — a flag that is never exercised is not an implementation.
"""
from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from policy_platform.api.roles import ADMIN, AUTHOR, POLICY_AUTHOR, READ, USE, VIEWER


# ── helpers ──────────────────────────────────────────────────────────

def _make_settings_dict(**overrides):
    """Minimal settings dict that keeps the app bootable."""
    defaults = {
        "database_url": "sqlite+aiosqlite:///unused",
        "alembic_database_url": "sqlite:///unused",
        "rbac_enabled": True,
        "dev_auth_enabled": True,
        "environment": "development",
    }
    defaults.update(overrides)
    return defaults


@contextmanager
def _patched_app(**settings_overrides):
    """Yield a TestClient whose settings patches stay active for requests.

    The enforce_rbac dependency calls get_settings() at request time, so
    the patch must survive beyond create_app() into the TestClient's
    request lifecycle.
    """
    from policy_platform.infrastructure.settings import Settings, get_settings
    from policy_platform.api.app import create_app

    get_settings.cache_clear()
    s = Settings(**_make_settings_dict(**settings_overrides))

    with patch("policy_platform.api.app.get_settings", return_value=s), \
         patch("policy_platform.api.authz.get_settings", return_value=s):
        app = create_app()
        yield TestClient(app, raise_server_exceptions=False)

    get_settings.cache_clear()


# ── default-deny guard test ──────────────────────────────────────────


def test_every_api_route_is_classified_in_the_operation_registry():
    """Fail when any API operation is absent from the registry.

    This is the default-deny guard: a newly added endpoint is
    unreachable until somebody classifies it. The floor assertion
    prevents a vacuous pass if route discovery silently returns nothing.
    """
    from policy_platform.api.authz import OPERATION_BANDS, _FRAMEWORK_PATHS

    with _patched_app(rbac_enabled=False) as c:
        app = c.app

    api_ops = []
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        if route.path in _FRAMEWORK_PATHS:
            continue
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            api_ops.append((method, route.path))

    assert len(api_ops) >= 90, (
        f"only found {len(api_ops)} API operations; expected at least 90. "
        "Route discovery may be broken."
    )

    unclassified = sorted(
        f"{m} {p}" for m, p in api_ops if (m, p) not in OPERATION_BANDS
    )
    assert unclassified == [], (
        f"{len(unclassified)} API operation(s) have no RBAC classification "
        f"and would be unreachable when enforcement is on:\n"
        + "\n".join(f"  {op}" for op in unclassified)
    )


# ── enforcement: flag off means no refusals ──────────────────────────


def test_rbac_off_allows_all_requests_without_credentials():
    """When rbac_enabled is False, behaviour is exactly as today."""
    with _patched_app(rbac_enabled=False) as c:
        resp = c.get("/health")
        assert resp.status_code == 200


# ── enforcement: viewer can read ─────────────────────────────────────


def test_viewer_can_access_read_endpoints():
    with _patched_app() as c:
        resp = c.get("/health", headers={"X-Dev-Role": VIEWER})
        assert resp.status_code == 200


# ── enforcement: viewer cannot author ────────────────────────────────


def test_viewer_is_refused_author_endpoints():
    """A viewer cannot reach an AUTHOR-band endpoint."""
    with _patched_app() as c:
        resp = c.post("/api/policy-sets", headers={"X-Dev-Role": VIEWER}, json={})
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "rbac_insufficient"
        assert detail["required_role"] == POLICY_AUTHOR
        assert detail["band"] == AUTHOR


# ── enforcement: policy_author can author ────────────────────────────


def test_policy_author_passes_author_band():
    """policy_author satisfies AUTHOR, even though the handler may fail
    for other reasons (missing body, no DB). 403 must not appear."""
    with _patched_app() as c:
        resp = c.post("/api/policy-sets", headers={"X-Dev-Role": POLICY_AUTHOR}, json={})
        # Anything but 403 — could be 422 (validation) or 500 (no DB).
        assert resp.status_code != 403


# ── enforcement: only admin can administer ───────────────────────────


def test_policy_author_cannot_administer():
    with _patched_app() as c:
        resp = c.delete("/api/policy-sets/test-key", headers={"X-Dev-Role": POLICY_AUTHOR})
        assert resp.status_code == 403
        assert resp.json()["detail"]["band"] == "ADMINISTER"


def test_admin_passes_administer_band():
    with _patched_app() as c:
        resp = c.delete("/api/policy-sets/test-key", headers={"X-Dev-Role": ADMIN})
        # Not 403 — whatever downstream error is fine.
        assert resp.status_code != 403


# ── enforcement: unknown role is default-closed ──────────────────────


def test_unknown_role_is_refused_even_for_read_band():
    with _patched_app() as c:
        resp = c.get("/health", headers={"X-Dev-Role": "superuser"})
        assert resp.status_code == 403


# ── enforcement: absent credentials default to viewer ────────────────


def test_no_credentials_defaults_to_viewer():
    """With no auth headers, the principal is viewer — READ works, AUTHOR does not."""
    with _patched_app() as c:
        resp = c.get("/health")
        assert resp.status_code == 200

        resp = c.post("/api/policy-sets", json={})
        assert resp.status_code == 403


# ── enforcement runs BEFORE handler side effects ─────────────────────


def test_refusal_arrives_before_handler_executes():
    """A 403 from the RBAC layer must arrive before any handler code runs.

    We test this by calling an AUTHOR endpoint as a viewer and verifying
    the 403 is immediate — no 500 from a missing database, which would
    mean the handler started executing before authorization checked.
    """
    with _patched_app() as c:
        resp = c.post(
            "/api/policy-sets",
            headers={"X-Dev-Role": VIEWER},
            json={"key": "test", "name": "Test"},
        )
        assert resp.status_code == 403, (
            f"expected 403 from RBAC before the handler ran, got {resp.status_code}"
        )


# ── principal resolution: EasyAuth ───────────────────────────────────


def test_easyauth_header_resolves_role():
    """X-MS-CLIENT-PRINCIPAL (base64 JSON) is decoded for the role claim."""
    with _patched_app(dev_auth_enabled=False) as c:
        payload = {
            "claims": [
                {"typ": "roles", "val": ADMIN},
                {"typ": "preferred_username", "val": "alice@example.com"},
            ]
        }
        header_value = base64.b64encode(json.dumps(payload).encode()).decode()
        resp = c.get("/health", headers={"X-MS-CLIENT-PRINCIPAL": header_value})
        assert resp.status_code == 200


def test_malformed_easyauth_defaults_to_viewer():
    with _patched_app(dev_auth_enabled=False) as c:
        resp = c.get("/health", headers={"X-MS-CLIENT-PRINCIPAL": "not-valid-base64!!!"})
        # viewer can read, so 200.
        assert resp.status_code == 200
        # But cannot author.
        resp = c.post(
            "/api/policy-sets",
            headers={"X-MS-CLIENT-PRINCIPAL": "not-valid-base64!!!"},
            json={},
        )
        assert resp.status_code == 403


# ── production safety ────────────────────────────────────────────────


def test_production_with_dev_auth_refuses_to_start():
    """The app must refuse to start in production with dev_auth_enabled."""
    with pytest.raises(RuntimeError, match="dev_auth_enabled"):
        with _patched_app(environment="production", dev_auth_enabled=True):
            pass


def test_production_without_dev_auth_boots_normally():
    """Production with dev_auth off is fine."""
    with _patched_app(environment="production", dev_auth_enabled=False) as c:
        assert c is not None


# ── registry completeness ────────────────────────────────────────────


def test_registry_covers_at_least_96_operations():
    """Positive control on the registry size — a silent shrinkage is caught."""
    from policy_platform.api.authz import OPERATION_BANDS
    assert len(OPERATION_BANDS) >= 96, (
        f"OPERATION_BANDS has {len(OPERATION_BANDS)} entries, expected >= 96"
    )


# ── scenario endpoints: the published-vs-draft surface distinction ───


def test_published_rule_scenario_is_viewer_reachable_but_draft_scenario_endpoints_are_not():
    """Three adjacent AI scenario endpoints in ai.py differ only in which
    surface they serve, and the RBAC band must reflect that — not whether
    they write (none of them do).

    * ``test-scenario`` targets a *published* version of a rule
      (``body.policy_version_id`` or the active version). That is the
      viewer's surface, so it is USE (viewer).
    * ``compute-scenario`` and ``evaluate-scenario`` take an unsaved rule
      payload from the request body — *"possibly still being edited, not
      yet saved"* — and exist to help a reviewer decide whether to approve
      a draft. A read-only endpoint whose only purpose is to serve an
      authoring decision inherits AUTHOR.

    This distinction is subtle and the three sit adjacent in ai.py, which
    is exactly why the error is easy to make. This test pins it so a
    future reclassification must be deliberate.
    """
    from policy_platform.api.authz import OPERATION_BANDS
    from policy_platform.api.roles import AUTHOR, USE

    # Published-rule scenario: viewer-reachable.
    assert OPERATION_BANDS[("POST", "/api/ai/policy-sets/{key}/rules/{rule_id}/test-scenario")] == USE

    # Draft-scoped scenario endpoints: AUTHOR only.
    assert OPERATION_BANDS[("POST", "/api/ai/rules/compute-scenario")] == AUTHOR
    assert OPERATION_BANDS[("POST", "/api/ai/rules/evaluate-scenario")] == AUTHOR
