"""Local authentication endpoints.

These exist so role-based access control can be exercised with real sign-ins
before Microsoft Entra is connected. The tokens they issue are validated by
the same path as Entra tokens — there is no bypass.

Both endpoints are classified as READ in OPERATION_BANDS. An unauthenticated
caller resolves to LEAST_PRIVILEGE (viewer), which satisfies READ — so the
login endpoint is reachable by someone who has not logged in yet, which it
obviously must be.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request

from policy_platform.api.authz import Principal, get_principal
from policy_platform.api.local_auth import authenticate, get_signing_key, load_accounts, mint_token
from policy_platform.infrastructure.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["system"])


def _as_iso(epoch_seconds: float) -> str:
    """The expiry as an ISO-8601 instant, which is what the wire carries.

    `mint_token` works in epoch seconds because a JWT's `exp` claim is numeric
    by specification, and that is the right type *inside* the token. It is the
    wrong type coming *out* of this endpoint: every other timestamp this API
    returns is `format: date-time`, so a float here is the one field a client
    has to special-case.

    It cost exactly that. The browser client declared `expires_at: string`,
    received a float, and its type check rejected the session it had just
    stored -- so a correct sign-in produced an interface that looked signed in,
    sent no credentials, and fell back to a stale role from an earlier build.
    Nothing failed loudly, which is why it survived a passing test suite.
    """

    return dt.datetime.fromtimestamp(epoch_seconds, tz=dt.timezone.utc).isoformat()


@router.post("/login")
async def login(request: Request):
    """Authenticate with username and password, returning a signed JWT."""
    settings = get_settings()
    if not settings.local_accounts_enabled:
        raise HTTPException(status_code=404, detail="Local authentication is not enabled")

    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    accounts = load_accounts(settings.local_accounts_file)
    account = authenticate(accounts, username, password)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    private_key = get_signing_key(settings.local_signing_key_file)
    token, expires_at = mint_token(
        private_key=private_key,
        username=account.username,
        role=account.role,
        issuer=settings.local_token_issuer,
        audience=settings.local_token_audience,
        ttl_minutes=settings.local_token_ttl_minutes,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": _as_iso(expires_at),
        "role": account.role,
        "name": account.username,
    }


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)):
    """Return the resolved principal for the calling user."""
    return {
        "name": principal.identity,
        "role": principal.role,
        "source": principal.source,
    }
