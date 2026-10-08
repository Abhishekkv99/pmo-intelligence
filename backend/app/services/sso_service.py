import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.user_repo import UserRepository
from app.models.enums import Role
from app.models.user import User
from app.utils.entitlements import (
    assert_may_sign_in,
    elevate_if_bootstrap_admin,
    is_bootstrap_admin,
)
from app.utils.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

MICROSOFT_LOGIN_BASE = "https://login.microsoftonline.com"

# The authority used when accounts from more than one tenant may sign in. It
# accepts any work or school account; which tenants are actually allowed is
# decided by the issuer check in validate_id_token, not by Microsoft.
MULTI_TENANT_AUTHORITY = "organizations"


def allowed_tenant_ids() -> list[str]:
    """Every Entra tenant whose accounts may sign in, home tenant first.

    The home tenant is always allowed; AZURE_ALLOWED_TENANT_IDS adds others.
    Entries are trimmed, lower-cased and deduplicated; empty ones are dropped.
    """
    tenants: list[str] = []
    extra = settings.azure_allowed_tenant_ids.split(",")
    candidates = [settings.azure_tenant_id, *extra]
    for raw in candidates:
        tenant = raw.strip().lower()
        if tenant and tenant not in tenants:
            tenants.append(tenant)
    return tenants


def sso_authority() -> str:
    """The path segment after login.microsoftonline.com for every SSO request.

    The home tenant ID while the app is single-tenant, so a registration that
    has not been made multi-tenant keeps working unchanged; "organizations"
    once any other tenant is allowed, because a tenant-specific authority
    refuses accounts from every other tenant before the app sees them
    (AADSTS50020) and a single-tenant registration refuses "organizations"
    (AADSTS50194).
    """
    if len(allowed_tenant_ids()) > 1:
        return MULTI_TENANT_AUTHORITY
    return settings.azure_tenant_id


def allowed_issuers() -> list[str]:
    """The id_token issuers accepted by validate_id_token, one per tenant."""
    return [f"{MICROSOFT_LOGIN_BASE}/{tenant}/v2.0" for tenant in allowed_tenant_ids()]


GUEST_MESSAGE = "Guest accounts cannot sign in to PMO Intelligence."

# The optional id-token claim the app registration adds
# (scripts/entra/Register-SsoApp.ps1): 0 for a member of the tenant, 1 for a
# guest. Entra may send it as a number or a string.
MEMBER_ACCOUNT = "0"


def assert_tenant_member(claims: dict[str, Any]) -> None:
    """Refuse a guest account, and any token without the ``acct`` claim.

    A missing claim is refused too (fail closed): it means the app
    registration has lost the optional claim, and letting the token through
    would let every guest in.
    """
    acct = claims.get("acct")
    if acct is not None and str(acct) == MEMBER_ACCOUNT:
        return
    logger.warning(
        "Sign-in refused: not a tenant member (acct=%s account=%s oid=%s)",
        acct,
        claims.get("preferred_username") or claims.get("email"),
        claims.get("oid"),
    )
    raise AuthorizationError(GUEST_MESSAGE)


def _token_url() -> str:
    return f"{MICROSOFT_LOGIN_BASE}/{sso_authority()}/oauth2/v2.0/token"


def _jwks_uri() -> str:
    return f"{MICROSOFT_LOGIN_BASE}/{sso_authority()}/discovery/v2.0/keys"


# Cache JWKS client (keys are cached internally by PyJWKClient)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Get or create a cached JWKS client for Microsoft Entra ID."""
    global _jwks_client  # noqa: PLW0603
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_jwks_uri(), cache_keys=True)
    return _jwks_client


class SSOService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens at Microsoft's /token endpoint."""
        token_data: dict[str, str] = {
            "client_id": settings.azure_client_id,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid email profile offline_access",
        }
        if settings.azure_client_secret:
            token_data["client_secret"] = settings.azure_client_secret

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_token_url(), data=token_data)

        if resp.status_code != 200:
            logger.error(
                "Microsoft token exchange failed: %s %s",
                resp.status_code,
                resp.text,
            )
            raise AuthenticationError("SSO token exchange failed")

        token_response: dict[str, Any] = resp.json()
        return token_response

    def validate_id_token(self, id_token: str) -> dict[str, Any]:
        """Validate the id_token signature, issuer, audience, and expiry.

        The issuer names the tenant the account belongs to, so checking it
        against ``allowed_issuers()`` is what keeps a multi-tenant
        registration closed to every organisation not on the list.

        Returns the decoded claims dict.
        """
        try:
            jwks_client = _get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)

            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.azure_client_id,
                issuer=allowed_issuers(),
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )

            # Verify required claims exist
            oid = claims.get("oid")
            if not oid:
                raise AuthenticationError("Missing oid claim in id_token")

            email = claims.get("email") or claims.get("preferred_username")
            if not email:
                raise AuthenticationError("Missing email claim in id_token")

            return claims

        except jwt.ExpiredSignatureError as err:
            raise AuthenticationError("SSO token has expired") from err
        except jwt.InvalidIssuerError as err:
            # The signature already verified, so the tenant claims are
            # trustworthy and worth logging: this is the line that tells an
            # operator which organisation to add to the allowlist.
            unverified = jwt.decode(id_token, options={"verify_signature": False})
            logger.warning(
                "SSO sign-in refused: tenant not allowed (tid=%s iss=%s upn=%s)",
                unverified.get("tid"),
                unverified.get("iss"),
                unverified.get("preferred_username") or unverified.get("email"),
            )
            raise AuthenticationError(
                "Your organisation is not allowed to sign in to this application"
            ) from err
        except jwt.InvalidTokenError as err:
            logger.error("SSO id_token validation failed: %s", err)
            raise AuthenticationError("Invalid SSO token") from err

    async def find_user_for_sign_in(self, claims: dict[str, Any]) -> User | None:
        """The user an SSO sign-in belongs to, or None when there is none.

        1. By Entra object id: a user who has signed in before.
        2. By email: a user a PMO manager created ahead of their first
           sign-in (``app.cli.user_role``), or a local account; the Entra id
           and the name from the token are linked to it.
        3. Otherwise a row is created only for a bootstrap admin, who gets
           ``pmo_manager`` at once. Nobody else gets a row: an unknown account
           is refused by the caller and leaves nothing behind.

        A listed bootstrap admin is raised to ``pmo_manager`` on every path.
        Whether the user may actually sign in is decided by the caller.
        """
        oid = claims["oid"]
        email = (claims.get("email") or claims.get("preferred_username", "")).lower()
        full_name = claims.get("name") or email.split("@")[0]

        user = await self.user_repo.get_by_entra_oid(oid)
        if user is None:
            user = await self.user_repo.get_by_email(email)
            if user is not None:
                # The role is left as it is: linking grants nothing
                user.entra_oid = oid
                user.auth_provider = "microsoft_entra"
                if claims.get("name"):
                    user.full_name = claims["name"]
                logger.info("Linked SSO to existing user: %s", email)
        if user is None:
            if not is_bootstrap_admin(email):
                return None
            user = await self.user_repo.create(
                email=email,
                hashed_password=None,
                full_name=full_name,
                auth_provider="microsoft_entra",
                entra_oid=oid,
                role=Role.PMO_MANAGER.value,
            )
            logger.info("Provisioned bootstrap admin on first sign-in: %s", email)
            return user
        elevate_if_bootstrap_admin(user)
        await self.session.flush()
        return user

    async def authenticate_sso(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> User:
        """Full SSO flow: code exchange, id_token validation, user provisioning."""
        # Step 1: Exchange authorization code for tokens
        token_response = await self.exchange_code_for_tokens(
            code, code_verifier, redirect_uri
        )

        id_token = token_response.get("id_token")
        if not id_token:
            raise AuthenticationError("No id_token in SSO response")

        # Step 2: Validate the id_token; members of the tenant only
        claims = self.validate_id_token(id_token)
        assert_tenant_member(claims)

        # Step 3: Find the user; refuse anyone without an active role
        user = assert_may_sign_in(
            await self.find_user_for_sign_in(claims),
            account=str(claims.get("preferred_username") or claims.get("email")),
            via="sso",
        )

        # Step 4: Store Microsoft tokens for Graph API (Teams integration)
        ms_access_token = token_response.get("access_token")
        ms_refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in")

        if ms_access_token:
            user.ms_access_token = ms_access_token
        if ms_refresh_token:
            user.ms_refresh_token = ms_refresh_token
        if expires_in:
            user.ms_token_expires_at = datetime.now(UTC) + timedelta(
                seconds=int(expires_in)
            )
        await self.session.flush()

        return user

    async def refresh_microsoft_token(self, user: User) -> str | None:
        """Refresh the Microsoft access token using the stored refresh token.

        Returns the new access token, or None if refresh fails.
        """
        if not user.ms_refresh_token:
            return None

        token_data: dict[str, str] = {
            "client_id": settings.azure_client_id,
            "grant_type": "refresh_token",
            "refresh_token": user.ms_refresh_token,
            "scope": "openid email profile offline_access",
        }
        if settings.azure_client_secret:
            token_data["client_secret"] = settings.azure_client_secret

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(_token_url(), data=token_data)

            if resp.status_code != 200:
                logger.warning("Microsoft token refresh failed: %s", resp.status_code)
                return None

            data = resp.json()
            user.ms_access_token = data.get("access_token")
            new_refresh = data.get("refresh_token")
            if new_refresh:
                user.ms_refresh_token = new_refresh
            expires_in = data.get("expires_in")
            if expires_in:
                user.ms_token_expires_at = datetime.now(UTC) + timedelta(
                    seconds=int(expires_in)
                )
            await self.session.flush()
            return user.ms_access_token
        except httpx.HTTPError:
            logger.exception("Error refreshing Microsoft token")
            return None
