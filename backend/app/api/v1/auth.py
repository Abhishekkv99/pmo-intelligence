from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import DbSession, get_current_user
from app.models.user import User
from app.rate_limiter import limiter
from app.schemas.auth import (
    LogoutResponse,
    SSOCallbackRequest,
    SSOConfigResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.sso_service import SSOService, sso_authority
from app.utils.exceptions import AuthenticationError

router = APIRouter()

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the httpOnly refresh token cookie on the response."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_expiration_days * 86400,
        domain=settings.cookie_domain or None,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain or None,
    )


def _require_local_auth() -> None:
    """Reject password sign-in when the deployment is SSO-only.

    Hiding the form in the frontend is presentation, not a boundary: the
    endpoints stay reachable to anyone with the URL. This is the boundary.
    """
    if not settings.local_auth_enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "Email and password sign-in is disabled. Please sign in with Microsoft."
            ),
        )


@router.post("/register", status_code=201, response_model=UserResponse)
@limiter.limit("3/minute")
async def register(
    request: Request,
    data: UserRegister,
    db: DbSession,
) -> UserResponse:
    """Register a new user account. Unavailable when local auth is disabled."""
    _require_local_auth()
    service = AuthService(db)
    user = await service.register(data)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    data: UserLogin,
    db: DbSession,
) -> TokenResponse:
    """Authenticate, receive a short-lived access token, and set a refresh cookie.

    Unavailable when local auth is disabled.
    """
    _require_local_auth()
    service = AuthService(db)
    user = await service.authenticate(data.email, data.password)

    # Short-lived access token (15 min)
    access_token = AuthService.create_access_token(user.id)

    # Opaque refresh token → hash and store in DB, send raw value as httpOnly cookie
    raw_refresh = AuthService.create_refresh_token()
    await service.store_refresh_token(user.id, raw_refresh)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    refresh_token: str | None = Cookie(None),
) -> TokenResponse | JSONResponse:
    """Rotate the refresh token and issue a new access token."""
    if refresh_token is None:
        raise AuthenticationError("Missing refresh token")

    service = AuthService(db)

    # Validate old token (revokes it) and get user_id
    try:
        user_id = await service.validate_and_rotate_refresh_token(refresh_token)
    except Exception:
        # Return a 401 JSONResponse directly (not via exception handler)
        # so the Set-Cookie header that clears the stale cookie is preserved.
        # Raising an exception would discard the injected Response object
        # and the browser would keep the stale cookie, causing redirect loops.
        error_response = JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired refresh token"},
        )
        error_response.delete_cookie(
            key=REFRESH_COOKIE_NAME,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path=REFRESH_COOKIE_PATH,
            domain=settings.cookie_domain or None,
        )
        return error_response

    # Issue new tokens
    access_token = AuthService.create_access_token(user_id)
    new_refresh = AuthService.create_refresh_token()
    await service.store_refresh_token(user_id, new_refresh)
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> LogoutResponse:
    """Revoke all refresh tokens for the current user and clear the cookie."""
    service = AuthService(db)
    revoked_count = await service.revoke_all_user_tokens(current_user.id)
    _clear_refresh_cookie(response)
    return LogoutResponse(
        message="Logged out successfully",
        revoked_tokens=revoked_count,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.get("/sso/microsoft/config", response_model=SSOConfigResponse)
async def sso_microsoft_config() -> SSOConfigResponse:
    """Return Microsoft Entra ID SSO configuration for the frontend."""
    if not settings.azure_client_id or not settings.azure_tenant_id:
        raise AuthenticationError("SSO is not configured")
    return SSOConfigResponse(
        client_id=settings.azure_client_id,
        tenant_id=settings.azure_tenant_id,
        authority=sso_authority(),
        redirect_uri=settings.azure_redirect_uri,
    )


@router.post("/sso/microsoft/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def sso_microsoft_callback(
    request: Request,
    response: Response,
    data: SSOCallbackRequest,
    db: DbSession,
) -> TokenResponse:
    """Exchange Microsoft SSO authorization code for app tokens."""
    sso_service = SSOService(db)
    user = await sso_service.authenticate_sso(
        code=data.code,
        code_verifier=data.code_verifier,
        redirect_uri=data.redirect_uri,
    )

    # Issue app tokens (same as email/password login); the service has
    # already refused guests and anyone without an active role
    access_token = AuthService.create_access_token(user.id)
    raw_refresh = AuthService.create_refresh_token()
    auth_service = AuthService(db)
    await auth_service.store_refresh_token(user.id, raw_refresh)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)
