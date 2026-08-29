"""A pre-shared subscription key is a credential, and is treated like one.

WHAT THIS MECHANISM IS FOR

Not every caller of the audited decision API is a person with a browser. An
agent, a workflow or a scheduled job needs to authenticate without an
interactive sign-in, and standing up an OIDC issuer to let one internal system
put a case to a project is a great deal of ceremony for a small need. So an
operator may configure one key, and a caller presenting it in
``X-Policy-Subscription-Key`` is a proved identity.

WHAT IT IS NOT

It is one key, for one configured identity, with one configured role. It does
not carry claims, it does not expire, it cannot be revoked without a restart,
and every caller holding it is the same principal in every receipt it produces.
Those are real limitations rather than oversights, and the tests below pin the
behaviour that keeps them honest — most importantly that a token naming a
*person* always wins over a key naming a system, so a shared credential can
never quietly take the blame for an individual's decision.

WHY EACH TEST HERE EXISTS

Every one of them is a way the mechanism could be wrong while looking right:

  * unconfigured and the header ignored → a deployment that never enabled the
    key silently accepts probes of it as anonymous requests;
  * a wrong key falling through → presenting a stale credential becomes
    indistinguishable from presenting none, and the integration appears to work
    until it meets an operation with a role;
  * the key beating a bearer token → an audited receipt names a shared system
    identity for a decision a named person made;
  * a bad token rescued by a good key → the no-fall-through rule that has
    protected the bearer path since it was written, quietly undone;
  * the audited routes not honouring it while ``rbac_enabled`` is off → the one
    deployment shape this feature was asked for.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from policy_platform.api import authz
from policy_platform.api.authz import (
    AUTHENTICATED_SOURCES,
    SUBSCRIPTION_KEY_HEADER,
    SUBSCRIPTION_KEY_SOURCE,
    Principal,
    get_principal,
    require_authenticated_principal,
)
from policy_platform.api.local_auth import get_signing_key, mint_token
from policy_platform.api.roles import ADMIN, POLICY_AUTHOR, VIEWER
from policy_platform.infrastructure.settings import Settings

CONFIGURED_KEY = "a-long-enough-pre-shared-key-value-0123456789"
CONFIGURED_IDENTITY = "expenses-agent"


def _settings(tmp_path, **overrides: Any) -> Settings:
    """A real `Settings`. The resolver reads a dozen fields across five branches,
    and a stand-in with four attributes would pass this file and fail the moment
    one more was consulted."""

    values: dict[str, Any] = {
        "database_url": "sqlite+aiosqlite:///unused",
        "alembic_database_url": "sqlite:///unused",
        "environment": "development",
        # On by default here, because `get_principal` short-circuits to a
        # permissive placeholder when enforcement is off — so with it false the
        # resolver never runs and these tests would assert nothing. The routes
        # that must authenticate *while* it is off are the audited ones, and
        # they are exercised through `require_authenticated_principal` below.
        "rbac_enabled": True,
        # On, so "the key outranks the development override" is testing
        # something rather than testing an absence.
        "dev_auth_enabled": True,
        "trust_platform_auth_header": False,
        "entra_issuer": None,
        "entra_audience": None,
        "entra_jwks_url": None,
        "local_accounts_enabled": True,
        "local_signing_key_file": str(tmp_path / "signing-key.pem"),
        "policy_subscription_key": CONFIGURED_KEY,
        "policy_subscription_key_identity": CONFIGURED_IDENTITY,
        "policy_subscription_key_role": VIEWER,
    }
    values.update(overrides)
    return Settings(**values)


def _token(settings: Settings, *, username: str, role: str) -> str:
    token, _ = mint_token(
        private_key=get_signing_key(settings.local_signing_key_file),
        username=username,
        role=role,
        issuer=settings.local_token_issuer,
        audience=settings.local_token_audience,
        ttl_minutes=30,
    )
    return token


def _app() -> FastAPI:
    """Two routes, one per dependency, and nothing else.

    The real application mounts a hundred routes behind a global guard; the two
    questions this file asks are "who does the resolver say this is?" and "does
    the audited-route dependency accept them?", and a minimal app answers both
    without dragging in a database.
    """

    app = FastAPI()

    @app.get("/who")
    def who(principal: Principal = Depends(get_principal)) -> dict:
        return {"identity": principal.identity, "role": principal.role, "source": principal.source}

    @app.get("/audited")
    def audited(principal: Principal = Depends(require_authenticated_principal)) -> dict:
        return {"identity": principal.identity, "role": principal.role, "source": principal.source}

    return app


@pytest.fixture
async def client(monkeypatch, tmp_path):
    """A client whose settings a test can replace in place.

    `configure` swaps what `authz.get_settings` returns, which is the single
    point every path in the resolver reads. Tests that need a token mint it
    against the settings they configured, so the signing key and the validator
    are always the same key.
    """

    state: dict[str, Settings] = {"settings": _settings(tmp_path)}
    monkeypatch.setattr(authz, "get_settings", lambda: state["settings"])

    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as http:

        def configure(**overrides: Any) -> Settings:
            state["settings"] = _settings(tmp_path, **overrides)
            return state["settings"]

        http.configure = configure  # type: ignore[attr-defined]
        http.settings = lambda: state["settings"]  # type: ignore[attr-defined]
        yield http


def _key(value: str) -> dict[str, str]:
    return {SUBSCRIPTION_KEY_HEADER: value}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── the mechanism is off until an operator turns it on ───────────────


async def test_with_no_key_configured_the_header_is_refused_not_ignored(client) -> None:
    """A credential that silently does nothing is worse than one that is refused.

    Ignoring it would let an integration point at a server that never enabled
    the mechanism, resolve to anonymous, and appear to work — right up until it
    reached an operation that needed a role, at which point the error would be
    about permissions and the fault would be about configuration.
    """

    client.configure(policy_subscription_key=None)

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "subscription_key_rejected"
    assert "not configured" in response.json()["detail"]["message"]


async def test_with_no_key_configured_an_ordinary_request_is_unaffected(client) -> None:
    """The control. The header being absent must change nothing at all."""

    client.configure(policy_subscription_key=None)

    response = await client.get("/who")

    assert response.status_code == 200
    assert response.json()["source"] == "unauthenticated"


async def test_a_configured_key_that_is_not_presented_changes_nothing(client) -> None:
    """Configuring the mechanism does not require using it."""

    response = await client.get("/who")

    assert response.status_code == 200
    assert response.json()["source"] == "unauthenticated"


# ── presenting the key ───────────────────────────────────────────────


async def test_a_valid_key_is_a_proved_identity(client) -> None:
    """The whole point: a caller with the key is somebody, not nobody."""

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json() == {
        "identity": CONFIGURED_IDENTITY,
        "role": VIEWER,
        "source": SUBSCRIPTION_KEY_SOURCE,
    }


def test_the_key_source_counts_as_proved_identity() -> None:
    """`AUTHENTICATED_SOURCES` is what the audited routes actually consult.

    Asserted directly as well as through a route, because a source that
    resolves correctly and is missing from this set produces a working
    `/api/auth/me` and a 401 on every decision — two symptoms that read as
    unrelated bugs.
    """

    assert SUBSCRIPTION_KEY_SOURCE in AUTHENTICATED_SOURCES
    assert "dev-header" not in AUTHENTICATED_SOURCES
    assert "unauthenticated" not in AUTHENTICATED_SOURCES


@pytest.mark.parametrize(
    "presented",
    [
        pytest.param(CONFIGURED_KEY[:-1], id="one-character-short"),
        pytest.param(CONFIGURED_KEY + "x", id="one-character-long"),
        pytest.param(CONFIGURED_KEY.upper(), id="wrong-case"),
        pytest.param("", id="empty-after-strip"),
        pytest.param("totally-different", id="unrelated"),
    ],
)
async def test_a_wrong_key_is_refused_and_never_falls_through(client, presented: str) -> None:
    """The rule the bearer path has always had, applied to the new credential.

    An empty value is the interesting case: it strips to nothing, so it must be
    treated as "no header" rather than compared — and it must not accidentally
    match an unconfigured server's empty key.
    """

    response = await client.get("/who", headers=_key(presented))

    if presented == "":
        # Nothing was really presented, so nothing is claimed. Anonymous, not a
        # match against the configured value.
        assert response.status_code == 200
        assert response.json()["source"] == "unauthenticated"
    else:
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "subscription_key_rejected"


async def test_a_wrong_key_does_not_reach_the_development_override(client) -> None:
    """A refused credential is refused, whatever else the request carries.

    `X-Dev-Role` is on in this fixture. If a rejected key fell through, a caller
    could present a bad key and a chosen role and be granted the role — the
    exact laundering the no-fall-through rule exists to stop.
    """

    response = await client.get(
        "/who", headers={**_key("wrong"), "X-Dev-Role": ADMIN}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "subscription_key_rejected"


async def test_the_key_outranks_the_development_override(client) -> None:
    """A real configured credential is not shadowed by a header anyone can set."""

    response = await client.get(
        "/who", headers={**_key(CONFIGURED_KEY), "X-Dev-Role": ADMIN}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == SUBSCRIPTION_KEY_SOURCE
    assert body["role"] == VIEWER
    assert body["identity"] == CONFIGURED_IDENTITY


def test_the_comparison_is_constant_time() -> None:
    """`==` on a secret leaks how long a guessed prefix was correct.

    The two values compared are a secret and an attacker-controlled string of
    the attacker's chosen length, which is exactly the shape a timing oracle
    needs. Asserted on the source because the property is about *how* the
    comparison is performed and cannot be observed from its result.
    """

    source = inspect.getsource(authz._try_subscription_key)
    assert "secrets.compare_digest" in source
    assert "presented == configured" not in source
    assert "presented != configured" not in source


# ── the configured role ──────────────────────────────────────────────


@pytest.mark.parametrize("role", [VIEWER, POLICY_AUTHOR, ADMIN])
async def test_the_configured_role_is_the_role_the_key_holds(client, role: str) -> None:
    """An operator decides what the key may do, and the default is the floor."""

    client.configure(policy_subscription_key_role=role)

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json()["role"] == role


def test_the_default_role_is_the_lowest_privilege(monkeypatch) -> None:
    """A bearer credential with no expiry should have the smallest blast radius.

    Read off `Settings` rather than off the fixture, so a default changed in the
    settings module fails here rather than being masked by an override.

    `_env_file=None` and the cleared environment matter: a developer who has
    configured a real key locally would otherwise see this test read *their*
    value and fail on it, which would teach them that the assertion is flaky
    rather than that the default is wrong.
    """

    for name in (
        "POLICY_SUBSCRIPTION_KEY",
        "POLICY_SUBSCRIPTION_KEY_IDENTITY",
        "POLICY_SUBSCRIPTION_KEY_ROLE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///unused",
        alembic_database_url="sqlite:///unused",
    )
    assert settings.policy_subscription_key is None
    assert settings.policy_subscription_key_role == VIEWER
    assert settings.policy_subscription_key_identity == "external-api-client"


async def test_a_role_this_product_does_not_define_refuses_the_key(client) -> None:
    """A typo in configuration is a configuration fault, reported as one.

    Left through, it produces a principal holding a role no band recognises —
    which is refused later by the capability layer with a message about
    permissions, sending the reader to look at the wrong thing entirely.
    """

    client.configure(policy_subscription_key_role="superuser")

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["code"] == "subscription_key_rejected"
    assert "role this product does not define" in detail["message"]


# ── interaction with a bearer token ──────────────────────────────────


async def test_a_valid_token_wins_over_a_valid_key(client) -> None:
    """A person outranks a shared system credential, deterministically.

    They are not equal evidence. A token names an individual, expires, and can
    be revoked at its issuer; the key names one configured system and does none
    of those. Resolving to the key would put a shared identity on a receipt for
    a decision a named person made — and would do it silently, because both
    credentials "worked".
    """

    token = _token(client.settings(), username="ana@example.com", role=POLICY_AUTHOR)

    response = await client.get("/who", headers={**_bearer(token), **_key(CONFIGURED_KEY)})

    assert response.status_code == 200
    body = response.json()
    assert body["identity"] == "ana@example.com"
    assert body["role"] == POLICY_AUTHOR
    assert body["source"] == "local-token"


async def test_a_bad_token_is_not_rescued_by_a_good_key(client) -> None:
    """The no-fall-through rule, in the direction it is easiest to lose.

    "Try the next credential" is how a rejected credential becomes an accepted
    request. A token that was presented and refused ends the request, even when
    a perfectly good key is sitting in the next header.
    """

    response = await client.get(
        "/who", headers={**_bearer("not-a-real-token"), **_key(CONFIGURED_KEY)}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "token_rejected"


async def test_a_key_still_works_when_no_token_is_offered(client) -> None:
    """The ordering must not have made the key unreachable."""

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json()["source"] == SUBSCRIPTION_KEY_SOURCE


# ── the two places the principal is consumed ─────────────────────────


async def test_the_audited_dependency_accepts_the_key_while_rbac_is_off(client) -> None:
    """The deployment shape this feature was asked for.

    With `rbac_enabled` false, `get_principal` hands back the permissive
    placeholder — and a receipt naming `rbac-disabled` as its caller is not a
    receipt. `require_authenticated_principal` resolves identity independently
    of the flag, which is what lets the audited routes demand a real caller on a
    deployment that has not switched enforcement on.
    """

    client.configure(rbac_enabled=False)

    response = await client.get("/audited", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json() == {
        "identity": CONFIGURED_IDENTITY,
        "role": VIEWER,
        "source": SUBSCRIPTION_KEY_SOURCE,
    }


async def test_with_rbac_off_an_ordinary_route_still_short_circuits(client) -> None:
    """The seam, asserted so nobody "fixes" it later.

    Adding a credential path must not make the global flag mean something new.
    With enforcement off, an ordinary route is permissive exactly as it was
    before this feature existed — the key changes what the *audited* routes can
    prove, not whether the product is enforcing anything.
    """

    client.configure(rbac_enabled=False)

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json()["source"] == "rbac-disabled"


async def test_with_rbac_off_a_wrong_key_does_not_reach_an_audited_route(client) -> None:
    """A refusal is a refusal on both sides of the flag."""

    client.configure(rbac_enabled=False)

    response = await client.get("/audited", headers=_key("wrong"))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "subscription_key_rejected"


async def test_the_audited_dependency_still_refuses_an_anonymous_caller(client) -> None:
    """The control on the test above. Adding a source must not open the gate."""

    response = await client.get("/audited")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert SUBSCRIPTION_KEY_HEADER in response.json()["detail"]["message"]


async def test_the_audited_dependency_still_refuses_the_development_override(client) -> None:
    """`X-Dev-Role` establishes no identity, and adding a real key path did not
    change that."""

    client.configure(rbac_enabled=False)

    response = await client.get("/audited", headers={"X-Dev-Role": ADMIN})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


async def test_the_key_authenticates_ordinary_routes_when_rbac_is_enabled(client) -> None:
    """The same key, the same identity, through the global guard's resolver.

    With enforcement on, `get_principal` is what every route reads. A key that
    authenticated only the two decision endpoints would mean an integration
    could put a case to a project and not resolve the project's own identity —
    two of the four calls in the documented flow.
    """

    client.configure(policy_subscription_key_role=POLICY_AUTHOR)

    response = await client.get("/who", headers=_key(CONFIGURED_KEY))

    assert response.status_code == 200
    assert response.json() == {
        "identity": CONFIGURED_IDENTITY,
        "role": POLICY_AUTHOR,
        "source": SUBSCRIPTION_KEY_SOURCE,
    }


async def test_with_rbac_enabled_a_wrong_key_is_still_refused(client) -> None:
    """Enforcement being on must not turn a refusal into a least-privilege grant."""

    response = await client.get("/who", headers=_key("wrong"))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "subscription_key_rejected"


# ── the key is never echoed ──────────────────────────────────────────


async def test_no_refusal_repeats_the_value_that_was_presented(client) -> None:
    """An error body travels into logs the caller does not own.

    The caller already knows what they sent; a server that quotes a presented
    credential back is one whose logs now contain other people's near-misses.
    """

    presented = "nearly-the-right-key-0123456789"
    response = await client.get("/who", headers=_key(presented))

    assert response.status_code == 401
    assert presented not in response.text
    assert CONFIGURED_KEY not in response.text
