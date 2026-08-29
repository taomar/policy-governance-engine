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

The ordering carries one decision worth naming: a credential that is presented
and rejected raises 401 rather than falling through to the weaker paths. That
holds for a bearer token and for the ``X-Policy-Subscription-Key`` pre-shared
key alike. Falling through would let an expired, forged or stale credential be
laundered into an anonymous-but-accepted request, and would make presenting a
bad one indistinguishable from presenting none.

Enforcement is only as good as the identity it reads, which is why all of them
default to off: ``rbac_enabled`` gates this module, with no issuer configured
the token path is not offered at all rather than half-checked, and with
``policy_subscription_key`` unset the subscription-key header is not read.
"""
from __future__ import annotations

import logging
import secrets
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
    ALL_ROLES,
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

__all__ = [
    "AUTHENTICATED_SOURCES",
    "SUBSCRIPTION_KEY_HEADER",
    "SUBSCRIPTION_KEY_SOURCE",
    "Principal",
    "enforce_rbac",
    "get_principal",
    "require_authenticated_principal",
    "OPERATION_BANDS",
]


#: Returned when RBAC is off — satisfies every band.
_PERMISSIVE_PRINCIPAL: Final[Principal] = Principal(
    role=ADMIN, identity="rbac-disabled", source="rbac-disabled"
)

#: The header a pre-shared subscription key arrives in.
#:
#: Not `Authorization`. A subscription key is not a bearer token — it has no
#: issuer, no expiry, no claims and no signature — and putting it in the same
#: header would mean every reader of this code, and every proxy rule written
#: against it, has to guess which of two unrelated credential formats a given
#: request carries. A distinct header makes the two paths separable in code, in
#: logs and in an ingress rule.
SUBSCRIPTION_KEY_HEADER: Final[str] = "X-Policy-Subscription-Key"

#: `Principal.source` for a caller proved by that key.
SUBSCRIPTION_KEY_SOURCE: Final[str] = "subscription-key"


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
    3. A configured subscription key in ``X-Policy-Subscription-Key``. A real
       credential, but a shared one naming a single system identity, so it
       sits below a token that names a person.
    4. The development override header, behind ``dev_auth_enabled`` and the
       startup check that refuses to boot with it on in production.
    5. The platform header, and **only** when someone has asserted that the
       ingress strips inbound copies. See `identity.py` for why that is not
       the default.
    6. Least privilege.

    A credential that is *presented and rejected* does not fall through to the
    weaker paths — this holds for a bearer token and for a subscription key
    alike. Falling through would mean an expired or forged credential could be
    laundered into an anonymous-but-accepted request, and worse, that presenting
    a bad one was indistinguishable from presenting none.
    """

    if not settings.rbac_enabled:
        return _PERMISSIVE_PRINCIPAL

    return _establish_principal(request, settings)


def _subscription_key_refused(message: str) -> HTTPException:
    """The one refusal shape a bad subscription key produces."""

    return HTTPException(
        status_code=401,
        detail={"code": "subscription_key_rejected", "message": message},
    )


def _try_subscription_key(presented: str, settings: Settings) -> Principal:
    """Check a presented key against the configured one, or raise 401.

    Called only when the caller actually sent the header, and only after the
    bearer paths above have declined to claim the request — see
    `_establish_principal` for why that order and not the reverse.

    THE COMPARISON

    `secrets.compare_digest` rather than `==`. The strings being compared are a
    secret and an attacker-controlled value of the attacker's chosen length,
    which is the exact shape a timing oracle needs: `==` returns as soon as two
    bytes differ, so the time it takes leaks how long a guessed prefix was
    correct. `compare_digest` does not short-circuit. Both sides are encoded to
    bytes first because it refuses mixed-width `str` inputs, and a caller can
    put any code point they like in a header.

    A REJECTED KEY DOES NOT FALL THROUGH

    Same rule the bearer path has held since this module was written, and for
    the same reason: if a wrong key quietly became an anonymous request, then
    presenting a bad credential would be indistinguishable from presenting
    none, and an integration with a stale key would look like it was working
    right up until it hit an operation that needed a role.

    THE CONFIGURED ROLE IS VALIDATED, NOT TRUSTED

    A typo in `POLICY_SUBSCRIPTION_KEY_ROLE` would otherwise produce a
    principal holding a role no band recognises. That is not a safe failure —
    it is an unreadable one, refused later by the capability layer with a
    message about permissions rather than about configuration — so it is
    refused here, where the fault actually is.
    """

    configured = (settings.policy_subscription_key or "").strip()
    if not secrets.compare_digest(presented.encode("utf-8"), configured.encode("utf-8")):
        logger.warning("Subscription key rejected")
        raise _subscription_key_refused("The subscription key is not valid.")

    role = (settings.policy_subscription_key_role or "").strip() or VIEWER
    if role not in ALL_ROLES:
        logger.error(
            "POLICY_SUBSCRIPTION_KEY_ROLE is %r, which is not one of %s; refusing the key",
            role,
            ", ".join(ALL_ROLES),
        )
        raise _subscription_key_refused(
            "The subscription key is configured with a role this product does not define, "
            "so it cannot be used until the deployment is corrected."
        )

    identity = (settings.policy_subscription_key_identity or "").strip() or "external-api-client"
    return Principal(role=role, identity=identity, source=SUBSCRIPTION_KEY_SOURCE)


def _establish_principal(request: Request, settings: Settings) -> Principal:
    """Steps 2–5 above, with the ``rbac_enabled`` short circuit removed.

    Split out because two questions were being answered by one function. "Is
    this request permitted under the global policy?" is what `_resolve_principal`
    asks, and when enforcement is off the honest answer is "yes, permissively".
    "Who *is* this?" is a different question, and it has a real answer whether
    or not global enforcement happens to be switched on.

    The audited decision endpoints ask the second question — a receipt that
    names `rbac-disabled` as the caller is not a receipt — so they call this
    directly through `require_authenticated_principal`. Nothing else should:
    bypassing the flag for an ordinary route would enable enforcement by the
    back door.

    WHERE THE SUBSCRIPTION KEY SITS IN THE ORDER

    After every bearer path and before the development override. Two decisions
    are packed into that placement:

    * **A valid bearer token wins over a subscription key.** They are not equal
      evidence: a token names a specific principal, expires, and can be revoked
      at its issuer; the key names one configured system identity and does
      none of those things. When a caller presents both, resolving to the
      weaker of the two would silently downgrade a request that carried proper
      credentials, and would make the receipt name a shared system identity for
      a decision a named person actually made. So the token is tried first, and
      a *valid* token means the key is never read at all.

      A token that is presented and rejected still refuses, exactly as it did
      before — a subscription key cannot rescue a bad token, because "try the
      next credential" is how a rejected credential gets laundered into an
      accepted request.

    * **It outranks the development override.** `X-Dev-Role` establishes no
      identity — it names the caller `dev-override` and lets anyone inside the
      perimeter choose their own role. A configured key is a real credential
      an operator deliberately installed, so it must not be shadowed by a
      header that is on by default in development.
    """

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

    # A subscription key, when one is configured and one was sent. Both halves
    # matter: with no key configured the header is not read at all, so a
    # deployment that never enabled the mechanism cannot be probed through it;
    # and with the header absent nothing here runs, so an ordinary browser
    # request is unaffected.
    presented_key = (request.headers.get(SUBSCRIPTION_KEY_HEADER) or "").strip()
    if presented_key and (settings.policy_subscription_key or "").strip():
        return _try_subscription_key(presented_key, settings)
    if presented_key:
        # Sent, but the server has no key. Refused rather than ignored: an
        # integration whose credential silently does nothing is one that
        # appears to work until it meets an operation with a role.
        logger.warning("Subscription key presented while none is configured")
        raise _subscription_key_refused(
            "Subscription-key authentication is not configured on this server."
        )

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
    # ── policy decisions (audited external case decisions) ───────────
    # Both bands are the floor, not the whole check. These two operations
    # additionally require a *valid authenticated principal* through
    # `require_authenticated_principal`, which holds even when global RBAC is
    # off — a receipt that cannot name who asked for it is not a receipt. The
    # POST is USE (it appends a decision record and alters no governed content);
    # the GET is READ at the band, with record-level ownership enforced in the
    # handler so one caller cannot read another's receipt.
    ("POST", "/api/policy-decisions/{project_key}/case"): USE,
    ("GET", "/api/policy-decisions/{decision_id}"): READ,
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


#: The `Principal.source` values that mean an identity was *proved*, not merely
#: accepted. A bearer token carries its own proof; the platform header is
#: believed only where an operator has asserted the edge strips inbound copies,
#: which is itself a deliberate act; and a subscription key is a secret only the
#: operator and the caller hold, compared in constant time.
#:
#: `dev-header` is absent on purpose. The development override establishes no
#: identity at all — it names the caller `dev-override` — so accepting it here
#: would write a receipt attributing an audited decision to a header anyone
#: inside the perimeter can set. `unauthenticated` is absent for the obvious
#: reason.
AUTHENTICATED_SOURCES: Final[frozenset[str]] = frozenset(
    {
        "token",
        "token-no-role",
        "local-token",
        "local-token-no-role",
        "platform-header",
        SUBSCRIPTION_KEY_SOURCE,
    }
)


def require_authenticated_principal(request: Request) -> Principal:
    """FastAPI dependency: the caller's proved identity, or 401.

    Used by the audited decision endpoints, which need something the global
    guard cannot give them. `enforce_rbac` answers "is this permitted?", and
    when `rbac_enabled` is off that answer is an unconditional yes carrying the
    placeholder principal `rbac-disabled`. Storing that in a receipt as the
    authenticated caller would be false, and returning a verdict against it
    would make an audited channel indistinguishable from an anonymous one.

    So this resolves identity independently of the flag and refuses when no
    identity was established. It never *grants* anything: capability remains the
    global guard's decision, and this only narrows who may reach the route.
    """

    principal = _establish_principal(request, get_settings())
    if principal.source not in AUTHENTICATED_SOURCES:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": (
                    "This operation records an audited decision receipt and requires an "
                    f"authenticated caller. Present a valid bearer token, or the "
                    f"{SUBSCRIPTION_KEY_HEADER} header when the operator has configured a "
                    "subscription key."
                ),
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


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
