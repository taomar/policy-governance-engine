"""RBAC enforcement layer: operation registry, principal resolution, and guard.

This module is the single enforcement point for role-based access control.
No individual router carries its own check (that pattern is how the previous
``actor_role`` guard reached only 3 of 48 writes and stopped). Instead,
every API operation is classified in the ``OPERATION_BANDS`` registry, and
a global FastAPI dependency checks the calling principal's role against the
band before any handler runs.

WHERE IDENTITY COMES FROM is decided in ``identity.py``, which validates a
bearer token when an issuer is configured — signature, expiry, issuer and
audience, with the algorithm pinned. This module only orders the sources
and turns the answer into a permission.

The ordering carries one decision worth naming: a token that is presented
and rejected raises 401 rather than falling through to the weaker paths.
Falling through would let an expired or forged token be laundered into an
anonymous-but-accepted request, and would make presenting a bad token
indistinguishable from presenting none.

Enforcement is only as good as the identity it reads, which is why both
default to off: ``rbac_enabled`` gates this module, and with no issuer
configured the token path is not offered at all rather than half-checked.
"""
from __future__ import annotations

import logging
from typing import Final

from fastapi import Depends, HTTPException, Request

from policy_platform.api.identity import (
    LEAST_PRIVILEGE,
    Principal,
    TokenRejected,
    bearer_token,
    decode_platform_header,
    identity_from_claims,
    role_from_claims,
    validate_bearer_token,
)
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
#
# `Principal` is defined in `identity.py` and re-exported here. It used to be
# declared in both, which is two descriptions of one thing: they agreed until
# one gained a field.

__all__ = ["Principal", "enforce_rbac", "get_principal", "OPERATION_BANDS"]


#: Returned when RBAC is off — satisfies every band.
_PERMISSIVE_PRINCIPAL: Final[Principal] = Principal(
    role=ADMIN, identity="rbac-disabled", source="rbac-disabled"
)


def _try_local_token(token: str, settings: Settings) -> Principal:
    """Validate a token against the local signing key, or raise 401.

    Factored out so both the Entra-fallback path and the local-only path
    call the same code without duplication.
    """
    from policy_platform.api.local_auth import get_signing_key

    try:
        local_public_key = get_signing_key(settings.local_signing_key_file).public_key()
        claims = validate_bearer_token(
            token,
            jwks_url="",
            issuer=settings.local_token_issuer,
            audience=settings.local_token_audience,
            key=local_public_key,
        )
    except TokenRejected as exc:
        logger.warning("Local token rejected: %s", exc)
        raise HTTPException(
            status_code=401,
            detail={"code": "token_rejected", "message": "The bearer token is not valid."},
        ) from exc

    role = role_from_claims(claims)
    if role is None:
        return Principal(
            role=VIEWER, identity=identity_from_claims(claims), source="local-token-no-role"
        )
    return Principal(role=role, identity=identity_from_claims(claims), source="local-token")


def _resolve_principal(request: Request, settings: Settings) -> Principal:
    """Determine who is calling and what role they hold.

    Order, strongest evidence first:

    1. ``rbac_enabled`` off → permissive; nothing is enforced.
    2. A validated bearer token, when an issuer is configured. This is the
       only path that establishes identity rather than accepting it, so it
       is tried before anything a proxy could have written.
    3. The development override header, behind ``dev_auth_enabled`` and the
       startup check that refuses to boot with it on in production.
    4. The platform header, and **only** when someone has asserted that the
       ingress strips inbound copies. See `identity.py` for why that is not
       the default.
    5. Least privilege.

    A token that is *presented and rejected* does not fall through to the
    weaker paths. Falling through would mean an expired or forged token
    could be laundered into an anonymous-but-accepted request, and worse,
    that presenting a bad token was indistinguishable from presenting none.
    """

    if not settings.rbac_enabled:
        return _PERMISSIVE_PRINCIPAL

    token = bearer_token(request.headers.get("Authorization"))
    issuer_configured = bool(
        settings.entra_issuer and settings.entra_audience and settings.entra_jwks_url
    )

    if token and issuer_configured:
        try:
            claims = validate_bearer_token(
                token,
                jwks_url=settings.entra_jwks_url or "",
                issuer=settings.entra_issuer or "",
                audience=settings.entra_audience or "",
            )
        except TokenRejected:
            # Entra rejected it. If local accounts are also configured, the
            # token may have been issued locally — try that before refusing.
            # This is not falling through to a weaker path: local tokens
            # carry the same proof, just a different issuer.
            if settings.local_accounts_enabled:
                return _try_local_token(token, settings)
            raise HTTPException(
                status_code=401,
                detail={"code": "token_rejected", "message": "The bearer token is not valid."},
            )

        role = role_from_claims(claims)
        if role is None:
            # Authenticated, and granted nothing here. That is a legitimate
            # state — a directory carries people who use other applications —
            # so it is least privilege rather than a refusal.
            return Principal(
                role=VIEWER, identity=identity_from_claims(claims), source="token-no-role"
            )
        return Principal(role=role, identity=identity_from_claims(claims), source="token")

    # Local tokens only (no Entra issuer configured). Same validation
    # path, different key source.
    if token and settings.local_accounts_enabled:
        return _try_local_token(token, settings)

    if settings.dev_auth_enabled:
        dev_role = request.headers.get("X-Dev-Role")
        if dev_role:
            return Principal(role=dev_role, identity="dev-override", source="dev-header")

    if settings.trust_platform_auth_header:
        raw = request.headers.get("X-MS-CLIENT-PRINCIPAL")
        if raw:
            claims = decode_platform_header(raw)
            if claims is None:
                logger.warning("Unreadable X-MS-CLIENT-PRINCIPAL; falling to least privilege")
            else:
                role = role_from_claims(claims) or VIEWER
                return Principal(
                    role=role, identity=identity_from_claims(claims), source="platform-header"
                )

    return LEAST_PRIVILEGE


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
    # ── auth ─────────────────────────────────────────────────────────
    # READ is correct: an unauthenticated caller resolves to LEAST_PRIVILEGE
    # (viewer), which satisfies READ — so the login endpoint is reachable by
    # someone who has not logged in yet, which it obviously must be.
    ("POST", "/api/auth/login"): READ,
    ("GET", "/api/auth/me"): READ,
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
    # ── policy review requests (viewer feedback) ─────────────────────
    # Submitting feedback is a viewer capability — the whole point of the
    # feature is that someone who cannot edit a policy can still flag concerns.
    ("POST", "/api/policy-review-requests"): USE,
    ("GET", "/api/policy-review-requests"): READ,
    # Acknowledging and resolving are author actions: only someone who can
    # change the policy should be able to act on feedback about it.
    ("POST", "/api/policy-review-requests/{request_id}/acknowledge"): AUTHOR,
    ("POST", "/api/policy-review-requests/{request_id}/resolve"): AUTHOR,
    # Withdrawing is a viewer action — the submitter retracts their own
    # open request. The band permits any viewer; the handler itself checks
    # that the caller is the submitter (record-level ownership, not band).
    ("DELETE", "/api/policy-review-requests/{request_id}"): USE,
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

    if settings.environment == "production" and settings.local_accounts_enabled:
        raise RuntimeError(
            "FATAL: local_accounts_enabled is True in a production environment. "
            "A plaintext credential file must not be available in production. "
            "Set LOCAL_ACCOUNTS_ENABLED=false or change ENVIRONMENT."
        )
