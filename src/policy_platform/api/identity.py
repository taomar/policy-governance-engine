"""Who is calling, established rather than accepted.

The capability layer in `authz.py` decides what a role may do. This module
decides what role the caller actually has, which is the harder half: a
capability check is only worth the confidence you have in the identity it
reads.

WHY A BEARER TOKEN AND NOT THE PLATFORM HEADER. Azure Container Apps'
built-in authentication injects `X-MS-CLIENT-PRINCIPAL` after it has
authenticated someone, and reading it is the obvious shortcut. The
deployment here makes that shortcut unsafe: the browser reaches an nginx
container, which proxies `/api/` to the API container, and nginx forwards
request headers it was not told to drop. A caller who sets that header
themselves has it delivered to the API alongside the genuine one. The API
being internal-only (`external: false`) does not help, because the web
container is inside the perimeter and forwards whatever it is given.

So the header is *not* trusted by default. `trust_platform_auth_header`
exists for deployments that have proven the edge strips inbound copies,
and it is off until someone asserts that on purpose. A signed token is
trusted instead: it carries its own proof, so it does not matter how many
hops it crossed or which of them were careless.

WHAT IS DELIBERATELY NOT HERE. No token cache beyond the JWKS client's
own, no refresh, no session. Every request is authorised on what it
presents. That is slower than a session and much easier to reason about,
and reasoning about it is the point.

WHEN NOTHING IS CONFIGURED the module resolves to the least privilege it
has, never the most. An unconfigured deployment is not an open one -- the
failure mode of a misconfigured identity provider must be that nobody can
do anything, not that everybody can.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass
from typing import Any, Final

from policy_platform.api.roles import ADMIN, ALL_ROLES, POLICY_AUTHOR, VIEWER

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Principal:
    """The resolved identity and role of the calling user.

    `source` records *how* the role was established. It is not decoration:
    a support question that begins "why can this person publish" is
    answered by which of the paths below produced the answer, and without
    it every path looks the same from the outside.
    """

    role: str
    identity: str = "anonymous"
    source: str = "anonymous"


#: What an unauthenticated or unresolvable caller gets. Named so the
#: intent is legible at the call sites: this is a decision, not a gap.
LEAST_PRIVILEGE: Final[Principal] = Principal(
    role=VIEWER, identity="anonymous", source="unauthenticated"
)


#: Entra app roles map onto this product's vocabulary by exact name, so an
#: operator configures roles once in the directory rather than maintaining
#: a translation table that can disagree with it. Anything unrecognised is
#: dropped rather than guessed at -- see `_role_from_claim_values`.
_KNOWN_ROLES: Final[frozenset[str]] = frozenset(ALL_ROLES)

#: Ranked so that a caller holding several roles gets the highest one they
#: were actually granted. Directories routinely assign more than one, and
#: taking the first of an unordered list would make a person's permissions
#: depend on claim ordering.
_ROLE_PRECEDENCE: Final[tuple[str, ...]] = (ADMIN, POLICY_AUTHOR, VIEWER)


def _role_from_claim_values(values: list[str]) -> str | None:
    """The highest known role among `values`, or None when there is none.

    Unknown names are ignored rather than refused. A directory will carry
    roles for other applications, and treating "Finance.Approver" as an
    error would make this product fail on a perfectly ordinary tenant.
    Ignoring them is safe because the result is only ever narrowed by it.
    """

    granted = {v for v in values if v in _KNOWN_ROLES}
    for role in _ROLE_PRECEDENCE:
        if role in granted:
            return role
    return None


def _claim_as_list(value: Any) -> list[str]:
    """Claims arrive as a list, or as one string, depending on the issuer.

    Normalised here so every caller below reads one shape. A string is not
    iterated character by character, which is the bug this exists to make
    impossible.
    """

    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def role_from_claims(claims: dict[str, Any]) -> str | None:
    """The role a validated token grants, or None if it grants none.

    `roles` is where Entra puts app-role assignments. `groups` is checked
    second for directories that model this with group membership named
    after the roles instead.
    """

    for key in ("roles", "groups"):
        role = _role_from_claim_values(_claim_as_list(claims.get(key)))
        if role is not None:
            return role
    return None


def identity_from_claims(claims: dict[str, Any]) -> str:
    """A name for the audit trail, preferring what a person would recognise."""

    for key in ("preferred_username", "upn", "email", "name", "sub", "oid"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def decode_platform_header(raw: str) -> dict[str, Any] | None:
    """Claims out of an `X-MS-CLIENT-PRINCIPAL` value, or None if unreadable.

    Returns None rather than raising for every malformed shape, because the
    caller's response to "unreadable" and to "absent" is the same, and a
    caller that has to catch three exception types to express that will
    eventually catch two.

    This decodes only. Whether the result may be *believed* is a separate
    decision, made by the resolver against `trust_platform_auth_header`.
    """

    try:
        decoded = json.loads(base64.b64decode(raw))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None

    # The platform's shape is a list of {typ, val} pairs. Flattened here so
    # the claim readers above work on it unchanged, whichever source the
    # claims came from.
    claims: dict[str, Any] = {}
    for entry in decoded.get("claims", []):
        if not isinstance(entry, dict):
            continue
        typ, val = entry.get("typ"), entry.get("val")
        if not isinstance(typ, str):
            continue
        # A repeated claim type is how multiple roles arrive; collect
        # rather than overwrite, or a user with two roles keeps only the
        # last one the encoder happened to emit.
        if typ in claims:
            existing = claims[typ]
            claims[typ] = (existing if isinstance(existing, list) else [existing]) + [val]
        else:
            claims[typ] = val

    # Entra's flattened form uses full claim URIs for some values; map the
    # two that matter onto the short names the readers above expect.
    _ALIASES = {
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/role": "roles",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": "name",
    }
    for uri, short in _ALIASES.items():
        if uri in claims and short not in claims:
            claims[short] = claims[uri]

    return claims


# ── bearer token validation ──────────────────────────────────────────


class TokenRejected(Exception):
    """A token was presented and is not acceptable.

    Distinct from "no token was presented". The two must not be collapsed:
    absence is an anonymous caller, whereas rejection is a caller asserting
    something untrue, and only the second is worth a log line.
    """


def _jwks_client(jwks_url: str):
    """A cached JWKS client for `jwks_url`.

    PyJWT's client caches signing keys itself; this only avoids rebuilding
    the client, and the cache is keyed by URL so a configuration change
    takes effect without a restart.
    """

    import jwt  # imported here so the module loads where PyJWT is absent

    client = _JWKS_CLIENTS.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url, cache_keys=True)
        _JWKS_CLIENTS[jwks_url] = client
    return client


_JWKS_CLIENTS: dict[str, Any] = {}


def validate_bearer_token(
    token: str,
    *,
    jwks_url: str,
    issuer: str,
    audience: str,
    key: Any = None,
    _key_resolver: Any = None,
) -> dict[str, Any]:
    """Claims from `token`, or raise `TokenRejected`.

    Every check is left to PyJWT rather than reimplemented: signature,
    expiry, not-before, issuer and audience. The one thing asserted here is
    that they are all *enabled*, because the failure this guards against is
    not a wrong implementation but a disabled one -- `verify_signature=False`
    is a single word, reads as configuration, and turns this function into
    an elaborate way of trusting the caller.

    `key` is the public key to verify the signature with. When supplied,
    the JWKS endpoint is not consulted — this is how locally issued tokens
    provide a known key without a network round-trip.

    `_key_resolver` is a legacy test seam kept for backward compatibility.
    Prefer `key` for new call sites.
    """

    import jwt

    try:
        if key is not None:
            signing_key = key
        elif _key_resolver is not None:
            signing_key = _key_resolver(token)
        else:
            signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key

        return jwt.decode(
            token,
            key=signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": True,
                "require": ["exp", "iss", "aud"],
            },
        )
    except Exception as exc:  # PyJWT raises a family; the response is one
        raise TokenRejected(str(exc)) from exc


def bearer_token(authorization_header: str | None) -> str | None:
    """The token out of an Authorization header, or None.

    Case-insensitive on the scheme because clients differ, and tolerant of
    surrounding whitespace for the same reason. Anything that is not a
    bearer scheme returns None rather than raising: another scheme is not a
    malformed bearer token, it is simply not one.
    """

    if not authorization_header:
        return None
    parts = authorization_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None

