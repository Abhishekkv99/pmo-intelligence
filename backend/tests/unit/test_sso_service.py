"""Unit tests for SSO service (token exchange, id_token validation, JIT)."""

import logging
import uuid
from contextlib import ExitStack
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.config import settings
from app.models.user import User
from app.services.sso_service import (
    SSOService,
    allowed_issuers,
    allowed_tenant_ids,
    assert_tenant_member,
    sso_authority,
)
from app.utils.exceptions import AuthenticationError, AuthorizationError


def _make_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "sso@example.com",
    auth_provider: str = "microsoft_entra",
    entra_oid: str | None = "oid-123",
    role: str | None = "sme",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.full_name = "SSO User"
    user.is_active = True
    user.auth_provider = auth_provider
    user.entra_oid = entra_oid
    user.role = role
    return user


class TestExchangeCodeForTokens:
    """Tests for SSOService.exchange_code_for_tokens."""

    async def test_successful_exchange_returns_token_response(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ms-access-token",
            "id_token": "ms-id-token",
            "token_type": "Bearer",
        }

        with patch("app.services.sso_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_ctx = mock_client_cls.return_value
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            result = await service.exchange_code_for_tokens(
                code="auth-code",
                code_verifier="verifier-123",
                redirect_uri="http://localhost:3000/auth/callback/microsoft",
            )

        assert result["id_token"] == "ms-id-token"
        assert result["access_token"] == "ms-access-token"

    async def test_exchange_asks_for_identity_scopes_only(self) -> None:
        service = SSOService(AsyncMock())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id_token": "ms-id-token"}

        with patch("app.services.sso_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_ctx = mock_client_cls.return_value
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            await service.exchange_code_for_tokens(
                code="auth-code",
                code_verifier="verifier-123",
                redirect_uri="http://localhost:3000/auth/callback/microsoft",
            )

        sent = mock_client.post.call_args.kwargs["data"]
        # No offline_access: PMO keeps no Microsoft refresh token
        assert sent["scope"] == "openid email profile"

    async def test_exchange_non_200_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        with patch("app.services.sso_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_ctx = mock_client_cls.return_value
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(AuthenticationError, match="SSO token exchange failed"):
                await service.exchange_code_for_tokens(
                    code="bad-code",
                    code_verifier="verifier",
                    redirect_uri="http://localhost:3000/callback",
                )

    async def test_exchange_sends_correct_form_data(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id_token": "token"}

        with patch("app.services.sso_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_ctx = mock_client_cls.return_value
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            await service.exchange_code_for_tokens(
                code="the-code",
                code_verifier="the-verifier",
                redirect_uri="http://localhost/callback",
            )

        call_kwargs = mock_client.post.call_args
        form_data = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data")
        assert form_data["code"] == "the-code"
        assert form_data["code_verifier"] == "the-verifier"
        assert form_data["redirect_uri"] == "http://localhost/callback"
        assert form_data["grant_type"] == "authorization_code"


class TestValidateIdToken:
    """Tests for SSOService.validate_id_token."""

    async def test_valid_token_returns_claims(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        expected_claims = {
            "oid": "oid-abc-123",
            "email": "user@company.com",
            "name": "Test User",
            "sub": "sub-123",
        }

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch("app.services.sso_service.jwt.decode", return_value=expected_claims),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            result = service.validate_id_token("fake.id.token")

        assert result["oid"] == "oid-abc-123"
        assert result["email"] == "user@company.com"

    async def test_missing_oid_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        claims_no_oid = {"email": "user@company.com", "name": "User"}
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch("app.services.sso_service.jwt.decode", return_value=claims_no_oid),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            with pytest.raises(AuthenticationError, match="Missing oid"):
                service.validate_id_token("token-no-oid")

    async def test_missing_email_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        claims_no_email = {"oid": "oid-123", "name": "User"}
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch("app.services.sso_service.jwt.decode", return_value=claims_no_email),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            with pytest.raises(AuthenticationError, match="Missing email"):
                service.validate_id_token("token-no-email")

    async def test_preferred_username_used_as_email_fallback(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        claims = {
            "oid": "oid-456",
            "preferred_username": "user@company.onmicrosoft.com",
            "name": "User",
        }
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch("app.services.sso_service.jwt.decode", return_value=claims),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            result = service.validate_id_token("token-with-upn")

        assert result["preferred_username"] == "user@company.onmicrosoft.com"

    async def test_expired_token_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch(
                "app.services.sso_service.jwt.decode",
                side_effect=jwt.ExpiredSignatureError("expired"),
            ),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            with pytest.raises(AuthenticationError, match="expired"):
                service.validate_id_token("expired.token")

    async def test_invalid_token_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch(
                "app.services.sso_service.jwt.decode",
                side_effect=jwt.InvalidTokenError("bad token"),
            ),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            with pytest.raises(AuthenticationError, match="Invalid SSO token"):
                service.validate_id_token("invalid.token")


class TestAssertTenantMember:
    """Guests are refused by the optional ``acct`` claim, failing closed."""

    @pytest.mark.parametrize("acct", [0, "0"])
    def test_member_passes(self, acct: object) -> None:
        assert_tenant_member({"oid": "o", "acct": acct})  # no exception

    @pytest.mark.parametrize("acct", [1, "1"])
    def test_guest_is_refused(
        self, acct: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="app.services.sso_service"),
            pytest.raises(AuthorizationError, match="Guest accounts cannot sign in"),
        ):
            assert_tenant_member(
                {"oid": "guest-oid", "acct": acct, "preferred_username": "g@x.com"}
            )
        assert "not a tenant member" in caplog.text
        assert "g@x.com" in caplog.text

    def test_missing_claim_is_refused(self) -> None:
        """A registration that lost the optional claim must not let guests in."""
        with pytest.raises(AuthorizationError, match="Guest accounts"):
            assert_tenant_member({"oid": "o", "email": "m@co.com"})


class TestFindUserForSignIn:
    """SSOService.find_user_for_sign_in: by oid, then email; new rows for
    bootstrap admins only."""

    async def test_existing_sso_user_returned_by_oid(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        existing_user = _make_mock_user(entra_oid="oid-existing")
        claims = {"oid": "oid-existing", "email": "user@co.com", "name": "User"}

        with (
            patch.object(
                service.user_repo, "get_by_entra_oid", return_value=existing_user
            ),
            patch.object(service.user_repo, "create") as mock_create,
        ):
            result = await service.find_user_for_sign_in(claims)

        assert result is existing_user
        mock_create.assert_not_called()

    async def test_user_created_ahead_is_linked_by_email(self) -> None:
        """A row granted a role by email gets the Entra id and real name."""
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        waiting = _make_mock_user(entra_oid=None, email="jane@co.com", role="sme")
        waiting.full_name = "jane"
        claims = {"oid": "new-oid-456", "email": "jane@co.com", "name": "Jane Doe"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=waiting),
        ):
            result = await service.find_user_for_sign_in(claims)

        assert result is waiting
        assert waiting.entra_oid == "new-oid-456"
        assert waiting.auth_provider == "microsoft_entra"
        assert waiting.full_name == "Jane Doe"
        assert waiting.role == "sme"

    async def test_linking_keeps_the_name_when_the_token_has_none(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        waiting = _make_mock_user(entra_oid=None, email="jane@co.com")
        waiting.full_name = "jane"
        claims = {"oid": "oid", "email": "jane@co.com"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=waiting),
        ):
            await service.find_user_for_sign_in(claims)

        assert waiting.full_name == "jane"

    async def test_unknown_account_gets_no_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "someone@else.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)
        claims = {"oid": "brand-new-oid", "email": "new@co.com", "name": "New User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(service.user_repo, "create") as mock_create,
        ):
            result = await service.find_user_for_sign_in(claims)

        assert result is None
        mock_create.assert_not_called()

    async def test_bootstrap_admin_is_created_as_pmo_manager(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "New@Co.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)
        new_user = _make_mock_user(email="new@co.com", role="pmo_manager")
        claims = {"oid": "brand-new-oid", "email": "NEW@co.com", "name": "New User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=new_user
            ) as mock_create,
        ):
            result = await service.find_user_for_sign_in(claims)

        assert result is new_user
        mock_create.assert_called_once_with(
            email="new@co.com",
            hashed_password=None,
            full_name="New User",
            auth_provider="microsoft_entra",
            entra_oid="brand-new-oid",
            role="pmo_manager",
        )

    async def test_bootstrap_admin_uses_email_prefix_when_name_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "jane.doe@company.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)
        claims = {"oid": "oid-no-name", "email": "jane.doe@company.com"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=_make_mock_user()
            ) as mock_create,
        ):
            await service.find_user_for_sign_in(claims)

        assert mock_create.call_args.kwargs["full_name"] == "jane.doe"

    async def test_email_lowercased_for_lookup(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)
        claims = {"oid": "oid-mixed", "email": "UPPER@CASE.COM", "name": "Upper"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(
                service.user_repo, "get_by_email", return_value=None
            ) as mock_by_email,
        ):
            await service.find_user_for_sign_in(claims)

        mock_by_email.assert_awaited_once_with("upper@case.com")

    async def test_listed_user_without_a_role_is_elevated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "boss@co.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)
        boss = _make_mock_user(email="boss@co.com", role=None)

        with patch.object(service.user_repo, "get_by_entra_oid", return_value=boss):
            result = await service.find_user_for_sign_in(
                {"oid": "oid-123", "email": "boss@co.com"}
            )

        assert result is boss
        assert boss.role == "pmo_manager"


class TestAuthenticateSSO:
    """Tests for SSOService.authenticate_sso (full flow)."""

    @staticmethod
    def _patched(
        service: SSOService, claims: dict[str, object], user: MagicMock | None
    ) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                service,
                "exchange_code_for_tokens",
                return_value={"id_token": "valid.id.token", "access_token": "ms-at"},
            )
        )
        stack.enter_context(
            patch.object(service, "validate_id_token", return_value=claims)
        )
        stack.enter_context(
            patch.object(service, "find_user_for_sign_in", return_value=user)
        )
        return stack

    async def _sign_in(self, service: SSOService) -> MagicMock:
        result = await service.authenticate_sso(
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="http://localhost/callback",
        )
        return cast("MagicMock", result)

    async def test_member_with_a_role_signs_in(self) -> None:
        service = SSOService(AsyncMock())
        user = _make_mock_user(role="ps")
        claims = {"oid": "oid-full", "email": "user@co.com", "acct": 0}

        with self._patched(service, claims, user):
            result = await self._sign_in(service)

        assert result is user

    async def test_sign_in_stores_no_microsoft_token(self) -> None:
        service = SSOService(AsyncMock())
        user = User(email="user@co.com", full_name="User", role="ps", is_active=True)
        claims = {"oid": "oid-full", "email": "user@co.com", "acct": 0}

        with self._patched(service, claims, cast("MagicMock", user)):
            await self._sign_in(service)

        assert not hasattr(user, "ms_access_token")
        assert not {"ms_access_token", "ms_refresh_token", "ms_token_expires_at"} & {
            c.name for c in User.__table__.columns
        }

    async def test_guest_is_refused_before_any_lookup(self) -> None:
        service = SSOService(AsyncMock())
        claims = {"oid": "guest", "email": "g@partner.com", "acct": 1}

        with (
            self._patched(service, claims, _make_mock_user(role="ps")),
            patch.object(service, "find_user_for_sign_in") as mock_find,
            pytest.raises(AuthorizationError, match="Guest accounts"),
        ):
            await self._sign_in(service)

        mock_find.assert_not_called()

    @pytest.mark.parametrize(
        ("role", "active"), [(None, True), ("sme", False), ("someone", True)]
    )
    async def test_user_without_an_active_role_is_refused(
        self, role: str | None, active: bool, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = SSOService(AsyncMock())
        user = _make_mock_user(role=role)
        user.is_active = active
        claims: dict[str, object] = {
            "oid": "oid-123",
            "preferred_username": "x@co.com",
            "acct": "0",
        }

        with (
            self._patched(service, claims, user),
            caplog.at_level(logging.WARNING, logger="app.utils.entitlements"),
            pytest.raises(AuthorizationError, match="has not been given access"),
        ):
            await self._sign_in(service)

        assert "Sign-in refused: no access (via=sso account=x@co.com" in caplog.text

    async def test_unknown_account_is_refused(self) -> None:
        service = SSOService(AsyncMock())
        claims = {"oid": "oid-new", "email": "new@co.com", "acct": 0}

        with (
            self._patched(service, claims, None),
            pytest.raises(AuthorizationError, match="has not been given access"),
        ):
            await self._sign_in(service)

    async def test_missing_id_token_raises_authentication_error(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        token_response = {"access_token": "ms-at"}  # no id_token

        with (
            patch.object(
                service,
                "exchange_code_for_tokens",
                return_value=token_response,
            ),
            pytest.raises(AuthenticationError, match="No id_token"),
        ):
            await service.authenticate_sso(
                code="code",
                code_verifier="verifier",
                redirect_uri="http://localhost/callback",
            )


class TestTenantAllowlist:
    """Tests for the multi-tenant allowlist (AZURE_ALLOWED_TENANT_IDS)."""

    def test_home_tenant_alone_when_no_extra_tenants(self) -> None:
        with (
            patch.object(settings, "azure_tenant_id", "home-tenant"),
            patch.object(settings, "azure_allowed_tenant_ids", ""),
        ):
            assert allowed_tenant_ids() == ["home-tenant"]
            assert sso_authority() == "home-tenant"
            assert allowed_issuers() == [
                "https://login.microsoftonline.com/home-tenant/v2.0"
            ]

    def test_extra_tenants_switch_to_the_organizations_authority(self) -> None:
        with (
            patch.object(settings, "azure_tenant_id", "home-tenant"),
            patch.object(settings, "azure_allowed_tenant_ids", "tenant-b, Tenant-C"),
        ):
            assert allowed_tenant_ids() == ["home-tenant", "tenant-b", "tenant-c"]
            assert sso_authority() == "organizations"
            assert allowed_issuers() == [
                "https://login.microsoftonline.com/home-tenant/v2.0",
                "https://login.microsoftonline.com/tenant-b/v2.0",
                "https://login.microsoftonline.com/tenant-c/v2.0",
            ]

    def test_blank_and_duplicate_entries_are_dropped(self) -> None:
        with (
            patch.object(settings, "azure_tenant_id", "Home-Tenant"),
            patch.object(
                settings, "azure_allowed_tenant_ids", " , home-tenant,,tenant-b,"
            ),
        ):
            assert allowed_tenant_ids() == ["home-tenant", "tenant-b"]

    def test_home_tenant_listed_again_does_not_make_the_app_multi_tenant(
        self,
    ) -> None:
        with (
            patch.object(settings, "azure_tenant_id", "home-tenant"),
            patch.object(settings, "azure_allowed_tenant_ids", "home-tenant"),
        ):
            assert sso_authority() == "home-tenant"

    async def test_token_from_a_tenant_not_on_the_list_is_refused(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        unverified: dict[str, object] = {
            "tid": "tenant-x",
            "iss": "https://login.microsoftonline.com/tenant-x/v2.0",
            "preferred_username": "someone@other.example",
        }

        def fake_decode(
            token: str, *args: object, **kwargs: object
        ) -> dict[str, object]:
            options = kwargs.get("options")
            if isinstance(options, dict) and options.get("verify_signature") is False:
                return unverified
            raise jwt.InvalidIssuerError("Invalid issuer")

        with (
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch("app.services.sso_service.jwt.decode", side_effect=fake_decode),
            caplog.at_level("WARNING"),
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            with pytest.raises(AuthenticationError, match="not allowed to sign in"):
                service.validate_id_token("fake.id.token")

        assert "tenant not allowed" in caplog.text
        assert "tid=tenant-x" in caplog.text
        assert "someone@other.example" in caplog.text

    async def test_issuer_check_uses_every_allowed_tenant(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        with (
            patch.object(settings, "azure_tenant_id", "home-tenant"),
            patch.object(settings, "azure_allowed_tenant_ids", "tenant-b"),
            patch("app.services.sso_service._get_jwks_client") as mock_jwks,
            patch(
                "app.services.sso_service.jwt.decode",
                return_value={"oid": "oid-1", "email": "u@b.example"},
            ) as mock_decode,
        ):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = (
                mock_signing_key
            )
            service.validate_id_token("fake.id.token")

        assert mock_decode.call_args.kwargs["issuer"] == [
            "https://login.microsoftonline.com/home-tenant/v2.0",
            "https://login.microsoftonline.com/tenant-b/v2.0",
        ]
