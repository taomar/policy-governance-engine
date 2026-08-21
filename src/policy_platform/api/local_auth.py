"""Local username/password authentication for development.

Mints real JWTs signed with a locally held RSA key so the token is validated
by the *same* ``validate_bearer_token`` used for Entra — same signature
check, same expiry, issuer and audience checks, same pinned algorithm. The
only difference is which key verifies it and who issued it.

This is deliberate: when Entra arrives, only the issuer changes. Everything
tested through this path is what will run in production, because there is no
"if local, skip validation" branch.

The accounts file is plaintext, gitignored, and read once at import time.
That is defensible for throwaway local credentials and for nothing else —
the startup guard refuses to load it in production.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import jwt

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocalAccount:
    username: str
    password: str
    role: str


def load_accounts(path: str) -> list[LocalAccount]:
    """Parse the accounts file, skipping malformed lines with a warning.

    An unreadable third line must not make the first two accounts unusable —
    a developer who fat-fingers one entry should not lose the session they
    were already using.
    """
    accounts: list[LocalAccount] = []
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Local accounts file %s does not exist", path)
        return accounts

    for lineno, raw in enumerate(filepath.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 3 or not all(parts):
            logger.warning("Skipping malformed line %d in %s", lineno, path)
            continue
        accounts.append(LocalAccount(username=parts[0], password=parts[1], role=parts[2]))
    return accounts


def authenticate(
    accounts: list[LocalAccount], username: str, password: str
) -> LocalAccount | None:
    """Return the matching account, or None.

    Uses ``secrets.compare_digest`` for password comparison so a wrong
    password and an unknown user take a similar amount of time — a login
    that answers "no such user" faster than "wrong password" tells an
    attacker which usernames exist.
    """
    # Always do a constant-time compare even for unknown users, so the
    # timing does not reveal whether the username was valid.
    found: LocalAccount | None = None
    for acct in accounts:
        if acct.username == username:
            found = acct
            break

    if found is None:
        # Burn the same time a real comparison would take.
        secrets.compare_digest("dummy-password", password)
        return None

    if secrets.compare_digest(found.password, password):
        return found
    return None


def _load_or_generate_key(path: str) -> rsa.RSAPrivateKey:
    """Load the RSA signing key, generating and persisting it on first use.

    Persisted so tokens survive an API restart — a developer being signed
    out by every reload makes the feature unusable for testing.
    """
    key_path = Path(path)
    if key_path.exists():
        return serialization.load_pem_private_key(  # type: ignore[return-value]
            key_path.read_bytes(), password=None
        )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    # Restrictive permissions where the platform supports it.
    try:
        os.chmod(str(key_path), 0o600)
    except OSError:
        pass  # Windows does not support POSIX permissions
    logger.info("Generated local signing key at %s", path)
    return private_key


def get_signing_key(path: str) -> rsa.RSAPrivateKey:
    """Public entry point — callers should not care about caching strategy."""
    return _load_or_generate_key(path)


def mint_token(
    *,
    private_key: rsa.RSAPrivateKey,
    username: str,
    role: str,
    issuer: str,
    audience: str,
    ttl_minutes: int,
) -> tuple[str, float]:
    """Create a signed JWT carrying the account's role. Returns (token, expires_at)."""
    now = time.time()
    expires_at = now + ttl_minutes * 60
    claims: dict[str, Any] = {
        "sub": username,
        "preferred_username": username,
        "roles": [role],
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    return token, expires_at
