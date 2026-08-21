"""Local authentication: real tokens, real validation, no bypass.

Every test here exercises the same validation path that Entra tokens will
use. That is the point of the design: what is tested now is what runs then.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from policy_platform.api.local_auth import (
    LocalAccount,
    authenticate,
    get_signing_key,
    load_accounts,
    mint_token,
)
from policy_platform.api.identity import TokenRejected, validate_bearer_token
from policy_platform.infrastructure.settings import get_settings


# ── helpers ──────────────────────────────────────────────────────────

def _enable_local_accounts(accounts_path: str, key_path: str):
    """Configure the environment for local auth and clear the settings cache."""
    os.environ["LOCAL_ACCOUNTS_ENABLED"] = "true"
    os.environ["LOCAL_ACCOUNTS_FILE"] = accounts_path
    os.environ["LOCAL_SIGNING_KEY_FILE"] = key_path
    os.environ["RBAC_ENABLED"] = "true"
    os.environ["DEV_AUTH_ENABLED"] = "false"
    os.environ["ENVIRONMENT"] = "development"
    get_settings.cache_clear()


def _write_accounts_file(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture()
def _local_auth_env(tmp_path):
    """Set up a temporary accounts file and signing key for local auth tests."""
    accounts_file = tmp_path / "accounts.txt"
    key_file = tmp_path / "signing-key.pem"
    _write_accounts_file(accounts_file, [
        "# test accounts",
        "alice:correcthorse:viewer",
        "bob:batterystable:policy_author",
        "carol:tr0ub4dor:admin",
    ])
    _enable_local_accounts(str(accounts_file), str(key_file))
    yield {
        "accounts_file": str(accounts_file),
        "key_file": str(key_file),
        "tmp_path": tmp_path,
    }


def _make_client() -> TestClient:
    """Build a fresh app so it picks up current settings."""
    get_settings.cache_clear()
    from policy_platform.api.app import create_app
    return TestClient(create_app())


# ── account loading ─────────────────────────────────────────────────


def test_a_correct_username_and_password_returns_a_token_the_real_validator_accepts(
    _local_auth_env,
):
    settings = get_settings()
    accounts = load_accounts(settings.local_accounts_file)
    account = authenticate(accounts, "alice", "correcthorse")
    assert account is not None

    private_key = get_signing_key(settings.local_signing_key_file)
    token, _ = mint_token(
        private_key=private_key,
        username=account.username,
        role=account.role,
        issuer=settings.local_token_issuer,
        audience=settings.local_token_audience,
        ttl_minutes=settings.local_token_ttl_minutes,
    )

    # Validated by the same function Entra tokens use — no bypass.
    claims = validate_bearer_token(
        token,
        jwks_url="",
        issuer=settings.local_token_issuer,
        audience=settings.local_token_audience,
        key=private_key.public_key(),
    )
    assert claims["sub"] == "alice"
    assert claims["roles"] == ["viewer"]


def test_token_carries_the_accounts_role_and_a_viewer_cannot_perform_author_operations(
    _local_auth_env,
):
    client = _make_client()

    # Log in as viewer
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "correcthorse"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert resp.json()["role"] == "viewer"

    headers = {"Authorization": f"Bearer {token}"}

    # Viewer can reach READ endpoints
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "viewer"

    # Viewer is refused an AUTHOR operation (e.g. create policy set)
    author_resp = client.post(
        "/api/policy-sets",
        headers=headers,
        json={"key": "test", "name": "test"},
    )
    assert author_resp.status_code == 403


def test_a_wrong_password_and_an_unknown_username_are_refused_identically(
    _local_auth_env,
):
    client = _make_client()

    wrong_pw = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrongpassword"}
    )
    unknown_user = client.post(
        "/api/auth/login", json={"username": "nonexistent", "password": "whatever"}
    )

    # Same status code and same detail shape — no information leak.
    assert wrong_pw.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_pw.json()["detail"] == unknown_user.json()["detail"]


def test_an_expired_locally_issued_token_is_refused(_local_auth_env):
    settings = get_settings()
    private_key = get_signing_key(settings.local_signing_key_file)

    # Mint a token that expired 10 minutes ago.
    now = time.time()
    claims = {
        "sub": "alice",
        "preferred_username": "alice",
        "roles": ["viewer"],
        "iss": settings.local_token_issuer,
        "aud": settings.local_token_audience,
        "iat": now - 1200,
        "exp": now - 600,
    }
    expired_token = jwt.encode(claims, private_key, algorithm="RS256")

    with pytest.raises(TokenRejected):
        validate_bearer_token(
            expired_token,
            jwks_url="",
            issuer=settings.local_token_issuer,
            audience=settings.local_token_audience,
            key=private_key.public_key(),
        )


def test_a_token_signed_by_a_different_key_is_refused(_local_auth_env):
    settings = get_settings()
    legitimate_key = get_signing_key(settings.local_signing_key_file)

    # Sign with a completely different key.
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = time.time()
    claims = {
        "sub": "alice",
        "preferred_username": "alice",
        "roles": ["viewer"],
        "iss": settings.local_token_issuer,
        "aud": settings.local_token_audience,
        "iat": now,
        "exp": now + 3600,
    }
    rogue_token = jwt.encode(claims, rogue_key, algorithm="RS256")

    with pytest.raises(TokenRejected):
        validate_bearer_token(
            rogue_token,
            jwks_url="",
            issuer=settings.local_token_issuer,
            audience=settings.local_token_audience,
            key=legitimate_key.public_key(),
        )


def test_the_app_refuses_to_start_with_local_accounts_enabled_in_production():
    os.environ["LOCAL_ACCOUNTS_ENABLED"] = "true"
    os.environ["ENVIRONMENT"] = "production"
    os.environ["DEV_AUTH_ENABLED"] = "false"
    get_settings.cache_clear()

    from policy_platform.api.app import create_app

    with pytest.raises(RuntimeError, match="local_accounts_enabled.*production"):
        create_app()


def test_a_malformed_line_does_not_stop_valid_accounts_loading(tmp_path):
    accounts_file = tmp_path / "accounts.txt"
    _write_accounts_file(accounts_file, [
        "good:password:viewer",
        "bad-line-no-colons",
        "also_good:password2:admin",
        "",
        "# comment",
        "missing_role:password:",
    ])

    accounts = load_accounts(str(accounts_file))
    assert len(accounts) == 2
    assert accounts[0].username == "good"
    assert accounts[1].username == "also_good"


def test_signing_key_persists_across_calls(tmp_path):
    key_path = str(tmp_path / "test-key.pem")
    key1 = get_signing_key(key_path)
    key2 = get_signing_key(key_path)

    # Same key material — token signed by first is verifiable by second.
    pub1 = key1.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    pub2 = key2.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    assert pub1 == pub2


def test_login_endpoint_is_unreachable_when_local_accounts_disabled():
    os.environ["LOCAL_ACCOUNTS_ENABLED"] = "false"
    os.environ["RBAC_ENABLED"] = "false"
    get_settings.cache_clear()

    from policy_platform.api.app import create_app

    client = TestClient(create_app())
    resp = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code == 404
