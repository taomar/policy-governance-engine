"""RBAC enforcement layer: operation registry, principal resolution, and guard.

This module is the single enforcement point for role-based access control.
No individual router carries its own check (that pattern is how the previous
``actor_role`` guard reached only 3 of 48 writes and stopped). Instead,
every API operation is classified in the ``OPERATION_BANDS`` registry, and
a global FastAPI dependency checks the calling principal's role against the
band before any handler runs.

AUTHENTICATION IS DEFERRED. The principal-resolution path trusts the
``X-MS-CLIENT-PRINCIPAL`` header injected by Azure Container Apps EasyAuth,
which means the platform has already validated the caller's identity. Real
JWT signature validation (``PyJWT`` against the Entra issuer keys, with
audience and issuer checks) is the next step. A half-validated token —
checking the signature but not the audience, or validating locally without
a key-rotation fetch — is worse than explicitly deferring, because it
creates confidence without correctness. This header path is intentionally
honest about what it does and does not verify.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Final

from fastapi import Depends, HTTPException, Request

from policy_platform.api.roles import (
    ADMIN,
    ADMINISTER,
    AUTHOR,
    BAND_MINIMUM_ROLE,
    POLICY_AUTHOR,
    RBAC_REFUSAL,
    READ,
    USE,
    VIEWER,
    role_satisfies,
)
from policy_platform.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# ── principal ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Principal:
    """The resolved identity and role of the calling user."""

    role: str
    identity: str = "anonymous"


#: Returned when RBAC is off — satisfies every band.
_PERMISSIVE_PRINCIPAL: Final[Principal] = Principal(role=ADMIN, identity="rbac-disabled")


def _resolve_principal(request: Request, settings: Settings) -> Principal:
    """Determine who is calling and what role they hold.

    Resolution order:
    1. When ``rbac_enabled`` is False → permissive (no enforcement).
    2. When ``dev_auth_enabled`` is True → read ``X-Dev-Role`` header.
    3. Read ``X-MS-CLIENT-PRINCIPAL`` (Azure Container Apps EasyAuth).
    4. Fall back to least privilege, never most.
    """
    if not settings.rbac_enabled:
        return _PERMISSIVE_PRINCIPAL

    # Development override — guarded by the startup check that refuses to
    # boot in production with dev_auth_enabled.
    if settings.dev_auth_enabled:
        dev_role = request.headers.get("X-Dev-Role")
        if dev_role:
            return Principal(role=dev_role, identity="dev-override")

    # Azure Container Apps EasyAuth injects this header after validating
    # the caller's identity. Its value is a base64-encoded JSON object
    # carrying the identity provider's claims.
    easyauth = request.headers.get("X-MS-CLIENT-PRINCIPAL")
    if easyauth:
        try:
            decoded = json.loads(base64.b64decode(easyauth))
            claims = {c["typ"]: c["val"] for c in decoded.get("claims", [])}
            role = claims.get("roles", VIEWER)
            identity = claims.get("preferred_username", claims.get("name", "easyauth-user"))
            return Principal(role=role, identity=identity)
        except Exception:
            logger.warning("Unparseable X-MS-CLIENT-PRINCIPAL header; defaulting to viewer")

    return Principal(role=VIEWER, identity="anonymous")


# ── operation registry ───────────────────────────────────────────────
#
# Keyed on (HTTP method, FastAPI path template). Every API operation must
# appear here; the default-deny guard test fails when one is missing.
#
# Classification rules (see the RBAC design doc for full reasoning):
#   - Do NOT classify by HTTP verb — many POST /api/ai/* endpoints are
#     POST only because they carry a request body, not because they write.
#   - Two axes; the stricter wins: (a) what does it change? (b) what
#     surface does it serve? A read-only endpoint whose purpose is to
#     compose a write inherits the permission of that write.

OPERATION_BANDS: Final[dict[tuple[str, str], str]] = {
    # ── system ───────────────────────────────────────────────────────
    ("GET", "/health"): READ,
    # ── AI: read / use (viewer) ──────────────────────────────────────
    ("POST", "/api/ai/ask"): USE,
    ("GET", "/api/ai/status"): READ,
    ("GET", "/api/ai/candidate-rules/{candidate_id}/explain-change"): READ,
    ("GET", "/api/ai/documents/{document_version_id}/extraction-progress"): READ,
    ("GET", "/api/ai/documents/{document_version_id}/extraction-runs"): READ,
    ("POST", "/api/ai/policy-case/answer"): USE,
    ("POST", "/api/ai/policy-sets/{key}/case-answer"): USE,
    ("GET", "/api/ai/policy-sets/{key}/candidates/quality"): READ,
    ("GET", "/api/ai/policy-sets/{key}/compare"): READ,
    ("GET", "/api/ai/policy-sets/{key}/correlate/findings"): READ,
    ("GET", "/api/ai/policy-sets/{key}/correlate/runs"): READ,
    ("GET", "/api/ai/policy-sets/{key}/quality"): READ,
    ("GET", "/api/ai/policy-sets/{key}/quality/history"): READ,
    ("GET", "/api/ai/policy-sets/{key}/quality/history/{run_id}"): READ,
    ("GET", "/api/ai/policy-sets/{key}/summary"): READ,
    ("POST", "/api/ai/provisions/{provision_id}/explain"): USE,
    ("POST", "/api/ai/rule-names/lookup"): READ,
    # compute-scenario and evaluate-scenario operate on a rule the caller
    # hands over — possibly unsaved, possibly a draft under review. Axis (a)
    # says viewer (changes nothing), but axis (b) says AUTHOR: both exist to
    # serve the draft-approval surface, and a read-only endpoint whose only
    # purpose is to help an authoring decision inherits that decision's band.
    # Contrast with test-scenario below, which targets a *published* version.
    ("POST", "/api/ai/rules/compute-scenario"): AUTHOR,
    ("POST", "/api/ai/rules/evaluate-scenario"): AUTHOR,
    # ── AI: author (policy_author) ───────────────────────────────────
    # rewrite endpoints exist to compose an edit to a candidate; AUTHOR
    # even though suggest_rewrite persists nothing, because their only
    # purpose is to prepare a governed-content change.
    ("POST", "/api/ai/candidate-rules/{candidate_id}/rewrite"): AUTHOR,
    ("POST", "/api/ai/candidate-rules/{candidate_id}/rewrite/apply"): AUTHOR,
    ("POST", "/api/ai/rules/rewrite-preview"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/documents/{document_version_id}/extract"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/topic-labels"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/rule-names"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/rules/draft-from-text"): AUTHOR,
    # test-scenario runs the deterministic engine against a *published*
    # version (body.policy_version_id or the active one). It persists nothing
    # and serves the viewer's surface — the product owner's stated grant is
    # "run a test case against policies". Contrast with compute-scenario and
    # evaluate-scenario above, which take an unsaved draft payload.
    ("POST", "/api/ai/policy-sets/{key}/rules/{rule_id}/test-scenario"): USE,
    ("POST", "/api/ai/policy-sets/{key}/quality/runs"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/candidates/quality/runs"): AUTHOR,
    ("POST", "/api/ai/policy-sets/{key}/correlate"): AUTHOR,
    ("POST", "/api/ai/correlate/findings/{finding_id}/disposition"): AUTHOR,
    # ── audit ────────────────────────────────────────────────────────
    ("GET", "/api/audit-events"): READ,
    # ── documents ────────────────────────────────────────────────────
    ("GET", "/api/documents"): READ,
    ("POST", "/api/documents/upload"): AUTHOR,
    ("PATCH", "/api/documents/{document_id}/assign"): AUTHOR,
    ("GET", "/api/documents/{document_version_id}/clauses"): READ,
    # ── evaluations ──────────────────────────────────────────────────
    # POST /evaluations runs the deterministic evaluator and appends an
    # audit row; it changes nothing governed, so it is USE, not AUTHOR.
    ("POST", "/api/evaluations"): USE,
    ("GET", "/api/evaluations/policy-sets/{key}"): READ,
    ("GET", "/api/evaluations/{evaluation_id}"): READ,
    # ── extraction ───────────────────────────────────────────────────
    ("GET", "/api/extraction/{document_version_id}/canonical"): READ,
    ("GET", "/api/extraction/{document_version_id}/coverage"): READ,
    ("GET", "/api/extraction/{document_version_id}/reading-plan"): READ,
    ("GET", "/api/extraction/{document_version_id}/structure"): READ,
    # ── notes ────────────────────────────────────────────────────────
    # Notes are collaboration artifacts, not governed content.
    # Creating one is USE (appends a record); deleting one is AUTHOR
    # because removal is a content-altering action.
    ("GET", "/api/notes"): READ,
    ("POST", "/api/notes"): USE,
    ("DELETE", "/api/notes/{note_id}"): AUTHOR,
    # ── policy attestations ──────────────────────────────────────────
    ("GET", "/api/policy-attestations/policy-sets/{key}"): READ,
    ("POST", "/api/policy-attestations/policy-sets/{key}/campaigns"): AUTHOR,
    ("GET", "/api/policy-attestations/search"): READ,
    # Acknowledging is recording that something was done, not authoring.
    ("POST", "/api/policy-attestations/{attestation_id}/acknowledge"): USE,
    # ── policy exceptions ────────────────────────────────────────────
    ("GET", "/api/policy-exceptions/policy-sets/{key}"): READ,
    ("POST", "/api/policy-exceptions/policy-sets/{key}"): AUTHOR,
    ("GET", "/api/policy-exceptions/{exception_id}"): READ,
    ("POST", "/api/policy-exceptions/{exception_id}/decide"): AUTHOR,
    # ── policy payload ───────────────────────────────────────────────
    ("GET", "/api/policy-payload/{provision_id}"): READ,
    # ── policy sets ──────────────────────────────────────────────────
    ("GET", "/api/policy-sets"): READ,
    ("POST", "/api/policy-sets"): AUTHOR,
    ("GET", "/api/policy-sets/portfolio/summary"): READ,
    ("DELETE", "/api/policy-sets/{key}"): ADMINISTER,
    ("GET", "/api/policy-sets/{key}"): READ,
    ("PATCH", "/api/policy-sets/{key}"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/active-version"): READ,
    ("GET", "/api/policy-sets/{key}/candidate-rules"): READ,
    ("POST", "/api/policy-sets/{key}/candidate-rules"): AUTHOR,
    ("POST", "/api/policy-sets/{key}/candidate-rules/bulk-review"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/candidate-rules/export"): READ,
    ("PUT", "/api/policy-sets/{key}/candidate-rules/{candidate_id}"): AUTHOR,
    ("POST", "/api/policy-sets/{key}/candidate-rules/{candidate_id}/override"): AUTHOR,
    ("POST", "/api/policy-sets/{key}/candidate-rules/{candidate_id}/request-changes"): AUTHOR,
    ("POST", "/api/policy-sets/{key}/candidate-rules/{candidate_id}/review"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/policies"): READ,
    ("GET", "/api/policy-sets/{key}/policy-index"): READ,
    ("POST", "/api/policy-sets/{key}/policy-index/rebuild"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/provisions/{provision_key}/history"): READ,
    ("POST", "/api/policy-sets/{key}/publish"): AUTHOR,
    ("POST", "/api/policy-sets/{key}/review"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/review-facets"): READ,
    ("GET", "/api/policy-sets/{key}/trusted-config"): READ,
    ("PUT", "/api/policy-sets/{key}/trusted-config"): ADMINISTER,
    ("GET", "/api/policy-sets/{key}/versions"): READ,
    ("POST", "/api/policy-sets/{key}/versions"): AUTHOR,
    ("GET", "/api/policy-sets/{key}/versions/{version_id}/export"): READ,
    ("GET", "/api/policy-sets/{key}/versions/{version_id}/policies"): READ,
    ("GET", "/api/policy-sets/{key}/versions/{version_id}/rules"): READ,
    ("GET", "/api/policy-sets/{key}/workspace-counts"): READ,
    # ── policy tests ─────────────────────────────────────────────────
    ("GET", "/api/policy-tests/policy-sets/{key}"): READ,
    ("POST", "/api/policy-tests/policy-sets/{key}"): AUTHOR,
    ("GET", "/api/policy-tests/policy-sets/{key}/failing"): READ,
    ("POST", "/api/policy-tests/policy-sets/{key}/propose"): AUTHOR,
    ("GET", "/api/policy-tests/policy-sets/{key}/validation-batches"): READ,
    ("POST", "/api/policy-tests/policy-sets/{key}/validation-batches"): AUTHOR,
    ("POST", "/api/policy-tests/validation-batches/{batch_id}/run"): USE,
    ("POST", "/api/policy-tests/{test_id}/review"): AUTHOR,
    ("POST", "/api/policy-tests/{test_id}/run"): USE,
    ("GET", "/api/policy-tests/{test_id}/runs"): READ,
}

#: Paths owned by the framework (OpenAPI docs, Swagger UI, ReDoc).
#: Enforcement is skipped for these because they carry no application
#: data and are not governed by RBAC.
_FRAMEWORK_PATHS: Final[frozenset[str]] = frozenset(
    {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
)


# ── enforcement dependency ───────────────────────────────────────────


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: resolve the calling principal."""
    return _resolve_principal(request, get_settings())


def enforce_rbac(request: Request, principal: Principal = Depends(get_principal)) -> None:
    """FastAPI global dependency: refuse when the principal lacks the capability.

    Runs before every handler. When ``rbac_enabled`` is False the principal
    is already permissive (admin), so every band is satisfied and no
    request is refused — the existing test suite runs unchanged.

    Matching uses the **route template** (``/api/policy-sets/{key}/publish``),
    not the raw URL, so path parameters do not break lookup.
    """
    settings = get_settings()
    if not settings.rbac_enabled:
        return

    route = request.scope.get("route")
    if route is None:
        return

    path_template = getattr(route, "path", None)
    if path_template is None:
        return

    # Framework routes (docs, openapi, redoc) are not governed.
    if path_template in _FRAMEWORK_PATHS:
        return

    method = request.method
    band = OPERATION_BANDS.get((method, path_template))

    if band is None:
        # Unclassified API route — default deny at runtime. The guard test
        # makes this unreachable in CI, but at runtime a newly deployed
        # endpoint that slipped past the test must not be open.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "unclassified_operation",
                "message": f"{method} {path_template} has no RBAC classification",
            },
        )

    minimum_role = BAND_MINIMUM_ROLE[band]
    if not role_satisfies(principal.role, minimum=minimum_role):
        raise HTTPException(
            status_code=403,
            detail={
                "code": RBAC_REFUSAL,
                "required_role": minimum_role,
                "band": band,
                "action": f"{method} {path_template}",
            },
        )


# ── startup safety ───────────────────────────────────────────────────


def validate_no_dev_auth_in_production(settings: Settings) -> None:
    """Refuse to start if the development bypass is on in production.

    A development header that can be switched on in production defeats
    the entire RBAC layer. This is a hard failure, not a warning,
    because the alternative is an operator who thinks enforcement is
    active while ``X-Dev-Role: admin`` bypasses it from any caller.
    """
    if settings.environment == "production" and settings.dev_auth_enabled:
        raise RuntimeError(
            "FATAL: dev_auth_enabled is True in a production environment. "
            "The X-Dev-Role header bypass must not be available in production. "
            "Set DEV_AUTH_ENABLED=false or change ENVIRONMENT."
        )
