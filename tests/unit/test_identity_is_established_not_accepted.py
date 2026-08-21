"""Identity is established from what a caller can prove, not what it claims.

These tests sign real tokens with a key generated here, so the checks below
exercise the same code path a deployment does. A test that stubs the
decoder proves the stub works.

The forged and expired cases matter more than the accepted one. A
validator that accepts a good token is easy to write by accident -- the
function that returns the claims without checking anything passes that test
too. What separates them is whether the bad tokens are refused, so most of
what follows is bad tokens.
"""
from __future__ import annotations

import datetime as dt

import pytest

jwt = pytest.importorskip("jwt", reason="PyJWT is required for the identity layer")
rsa = pytest.importorskip(
    "cryptography.hazmat.primitives.asymmetric.rsa",
    reason="cryptography is required to sign test tokens",
)

from policy_platform.api.identity import (  # noqa: E402
    LEAST_PRIVILEGE,
    TokenRejected,
    bearer_token,
    decode_platform_header,
    identity_from_claims,
    role_from_claims,
    validate_bearer_token,
)
from policy_platform.api.roles import ADMIN, POLICY_AUTHOR, VIEWER  # noqa: E402

ISSUER = "https://login.microsoftonline.com/tenant-id/v2.0"
AUDIENCE = "api://policy-platform"


@pytest.fixture(scope="module")
def keypair():
    """One RSA key for the whole module. Generating 2048 bits per test is
    slow enough to discourage writing more of them, which is the wrong
    incentive for a security file."""

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture(scope="module")
def other_keypair():
    """A second key, for the forgery case. The attacker's signature is
    well-formed; it is simply not from the issuer."""

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _token(private_key, **overrides) -> str:
    now = dt.datetime.now(tz=dt.timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": now + dt.timedelta(minutes=10),
        "nbf": now - dt.timedelta(minutes=1),
        "iat": now,
        "preferred_username": "someone@example.com",
        "roles": ["policy_author"],
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def _accepts(public_key):
    """A key resolver standing in for the JWKS lookup, so these tests do not
    reach the network. The signature check it feeds is the real one."""

    return lambda _token: public_key


class TestAValidTokenIsAccepted:
    def test_claims_come_back_from_a_properly_signed_token(self, keypair):
        private, public = keypair
        claims = validate_bearer_token(
            _token(private),
            jwks_url="unused",
            issuer=ISSUER,
            audience=AUDIENCE,
            _key_resolver=_accepts(public),
        )

        assert claims["preferred_username"] == "someone@example.com"
        assert claims["roles"] == ["policy_author"]


class TestATokenThatProvesNothingIsRefused:
    def test_a_token_signed_by_another_key_is_refused(self, keypair, other_keypair):
        """The forgery case. Everything is well-formed except who signed it."""

        _, public = keypair
        forger_private, _ = other_keypair

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                _token(forger_private),
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_an_expired_token_is_refused(self, keypair):
        private, public = keypair
        past = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=1)

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                _token(private, exp=past),
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_a_token_for_another_audience_is_refused(self, keypair):
        """A token minted for a different application is a real token. It is
        simply not addressed to this one, and accepting it would let any
        tenant application's token act here."""

        private, public = keypair

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                _token(private, aud="api://some-other-app"),
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_a_token_from_another_issuer_is_refused(self, keypair):
        private, public = keypair

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                _token(private, iss="https://evil.example.com/v2.0"),
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_an_unsigned_token_is_refused(self, keypair):
        """`alg: none` is the oldest attack on this format and the reason the
        algorithm list is fixed rather than read from the token's header."""

        _, public = keypair
        now = dt.datetime.now(tz=dt.timezone.utc)
        unsigned = jwt.encode(
            {
                "iss": ISSUER,
                "aud": AUDIENCE,
                "exp": now + dt.timedelta(minutes=10),
                "roles": ["admin"],
            },
            key="",
            algorithm="none",
        )

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                unsigned,
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_a_token_with_no_expiry_is_refused(self, keypair):
        """A token that never expires is a password with extra steps."""

        private, public = keypair
        now = dt.datetime.now(tz=dt.timezone.utc)
        forever = jwt.encode(
            {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "roles": ["admin"]},
            private,
            algorithm="RS256",
        )

        with pytest.raises(TokenRejected):
            validate_bearer_token(
                forever,
                jwks_url="unused",
                issuer=ISSUER,
                audience=AUDIENCE,
                _key_resolver=_accepts(public),
            )

    def test_rubbish_is_refused_rather_than_crashing(self, keypair):
        _, public = keypair
        for value in ("", "not-a-token", "a.b.c", "..."):
            with pytest.raises(TokenRejected):
                validate_bearer_token(
                    value,
                    jwks_url="unused",
                    issuer=ISSUER,
                    audience=AUDIENCE,
                    _key_resolver=_accepts(public),
                )


class TestTheRoleAClaimGrants:
    def test_the_highest_granted_role_wins(self):
        """Directories assign several roles routinely. Taking the first of an
        unordered list would make a person's permissions depend on claim
        ordering, which is nobody's intent."""

        assert role_from_claims({"roles": ["viewer", "admin", "policy_author"]}) == ADMIN
        assert role_from_claims({"roles": ["viewer", "policy_author"]}) == POLICY_AUTHOR
        assert role_from_claims({"roles": ["viewer"]}) == VIEWER

    def test_a_single_string_claim_is_not_read_character_by_character(self):
        assert role_from_claims({"roles": "admin"}) == ADMIN

    def test_roles_belonging_to_other_applications_are_ignored(self):
        """A tenant carries roles for everything it runs. Refusing an
        unfamiliar one would make this product fail on an ordinary
        directory; ignoring it only ever narrows the result."""

        assert role_from_claims({"roles": ["Finance.Approver", "policy_author"]}) == POLICY_AUTHOR

    def test_a_token_granting_no_known_role_grants_none(self):
        """Not an error, and not viewer either. The caller is authenticated
        and has no role here, which the resolver turns into least privilege
        -- but this function must say 'none' so the two stay distinguishable."""

        assert role_from_claims({"roles": ["Finance.Approver"]}) is None
        assert role_from_claims({}) is None

    def test_groups_are_read_when_roles_are_absent(self):
        assert role_from_claims({"groups": ["policy_author"]}) == POLICY_AUTHOR


class TestTheNameForTheAuditTrail:
    def test_the_most_recognisable_name_is_preferred(self):
        assert identity_from_claims({"preferred_username": "a@b.com", "sub": "xyz"}) == "a@b.com"
        assert identity_from_claims({"sub": "xyz"}) == "xyz"

    def test_an_empty_claim_set_still_produces_something_loggable(self):
        assert identity_from_claims({}) == "unknown"


class TestTheAuthorizationHeader:
    def test_a_bearer_token_is_extracted_whatever_the_casing(self):
        assert bearer_token("Bearer abc") == "abc"
        assert bearer_token("bearer abc") == "abc"
        assert bearer_token("  Bearer   abc  ") == "abc"

    def test_another_scheme_is_not_a_malformed_bearer_token(self):
        assert bearer_token("Basic dXNlcjpwYXNz") is None

    def test_nothing_is_extracted_from_nothing(self):
        assert bearer_token(None) is None
        assert bearer_token("") is None
        assert bearer_token("Bearer") is None
        assert bearer_token("Bearer   ") is None


class TestThePlatformHeader:
    def test_claims_are_read_out_of_the_platform_shape(self):
        import base64
        import json

        raw = base64.b64encode(
            json.dumps(
                {
                    "claims": [
                        {"typ": "preferred_username", "val": "someone@example.com"},
                        {"typ": "roles", "val": "policy_author"},
                    ]
                }
            ).encode()
        ).decode()

        claims = decode_platform_header(raw)
        assert claims is not None
        assert identity_from_claims(claims) == "someone@example.com"
        assert role_from_claims(claims) == POLICY_AUTHOR

    def test_a_repeated_claim_type_keeps_every_value(self):
        """Multiple roles arrive as the same claim type repeated. Overwriting
        would silently keep whichever the encoder emitted last, which is how
        an admin quietly becomes a viewer -- or the reverse."""

        import base64
        import json

        raw = base64.b64encode(
            json.dumps(
                {
                    "claims": [
                        {"typ": "roles", "val": "viewer"},
                        {"typ": "roles", "val": "admin"},
                    ]
                }
            ).encode()
        ).decode()

        assert role_from_claims(decode_platform_header(raw)) == ADMIN

    def test_unreadable_values_return_nothing_rather_than_raising(self):
        for value in ("", "not-base64!!", "YWJj", "e30="):
            assert decode_platform_header(value) in (None, {})


class TestTheDefault:
    def test_the_unresolved_caller_gets_the_least_privilege_there_is(self):
        """The failure mode of a misconfigured identity provider has to be
        that nobody can do anything, not that everybody can."""

        assert LEAST_PRIVILEGE.role == VIEWER
        assert LEAST_PRIVILEGE.role != ADMIN
