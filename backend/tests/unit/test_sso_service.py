"""Unit tests for SSO service (token exchange, id_token validation, JIT)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.config import settings
from app.services.sso_service import (
    SSOService,
    allowed_issuers,
    allowed_tenant_ids,
    sso_authority,
)
from app.utils.exceptions import AuthenticationError


def _make_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "sso@example.com",
    auth_provider: str = "microsoft_entra",
    entra_oid: str = "oid-123",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.full_name = "SSO User"
    user.is_active = True
    user.auth_provider = auth_provider
    user.entra_oid = entra_oid
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


class TestGetOrCreateUser:
    """Tests for SSOService.get_or_create_user (JIT provisioning + auto-linking)."""

    async def test_existing_sso_user_returned_by_oid(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        existing_user = _make_mock_user(entra_oid="oid-existing")
        claims = {"oid": "oid-existing", "email": "user@co.com", "name": "User"}

        with patch.object(
            service.user_repo, "get_by_entra_oid", return_value=existing_user
        ):
            result = await service.get_or_create_user(claims)

        assert result == existing_user

    async def test_existing_local_user_auto_linked_by_email(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        local_user = _make_mock_user(
            auth_provider="local", entra_oid=None, email="local@co.com"
        )
        claims = {"oid": "new-oid-456", "email": "local@co.com", "name": "Local User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=local_user),
        ):
            result = await service.get_or_create_user(claims)

        assert result == local_user
        assert local_user.entra_oid == "new-oid-456"
        assert local_user.auth_provider == "microsoft_entra"
        mock_session.flush.assert_called_once()

    async def test_new_user_jit_provisioned(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user(email="new@co.com")
        claims = {"oid": "brand-new-oid", "email": "new@co.com", "name": "New User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=new_user
            ) as mock_create,
        ):
            result = await service.get_or_create_user(claims)

        assert result == new_user
        mock_create.assert_called_once_with(
            email="new@co.com",
            hashed_password=None,
            full_name="New User",
            auth_provider="microsoft_entra",
            entra_oid="brand-new-oid",
        )

    async def test_jit_provision_elevates_bootstrap_admin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "New@Co.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user(email="new@co.com")
        new_user.role = None
        claims = {"oid": "brand-new-oid", "email": "new@co.com", "name": "New User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(service.user_repo, "create", return_value=new_user),
        ):
            result = await service.get_or_create_user(claims)

        assert result is new_user
        assert new_user.role == "pmo_manager"
        mock_session.flush.assert_awaited_once()

    async def test_jit_provision_leaves_unlisted_user_without_a_role(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "someone@else.com")
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user(email="new@co.com")
        new_user.role = None
        claims = {"oid": "brand-new-oid", "email": "new@co.com", "name": "New User"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(service.user_repo, "create", return_value=new_user),
        ):
            await service.get_or_create_user(claims)

        assert new_user.role is None
        mock_session.flush.assert_not_awaited()

    async def test_jit_provision_uses_email_prefix_when_name_missing(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user()
        claims = {"oid": "oid-no-name", "email": "jane.doe@company.com"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=new_user
            ) as mock_create,
        ):
            await service.get_or_create_user(claims)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["full_name"] == "jane.doe"

    async def test_email_lowercased_for_lookup(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user()
        claims = {"oid": "oid-mixed", "email": "UPPER@CASE.COM", "name": "Upper"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=new_user
            ) as mock_create,
        ):
            await service.get_or_create_user(claims)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["email"] == "upper@case.com"

    async def test_jit_provision_never_sets_a_role_on_creation(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        new_user = _make_mock_user(email="jane@informationtechconsultants.com")
        claims = {
            "oid": "oid-itc",
            "email": "Jane@InformationTechConsultants.com",
            "name": "Jane",
        }

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=new_user
            ) as mock_create,
        ):
            await service.get_or_create_user(claims)

        assert "role" not in mock_create.call_args.kwargs

    async def test_auto_link_leaves_the_existing_role_untouched(self) -> None:
        """An existing row keeps its role when SSO is linked to it."""
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        local_user = _make_mock_user(
            auth_provider="local", entra_oid=None, email="override@gmail.com"
        )
        local_user.role = "tech_lead"
        claims = {"oid": "oid-link", "email": "override@gmail.com", "name": "O"}

        with (
            patch.object(service.user_repo, "get_by_entra_oid", return_value=None),
            patch.object(service.user_repo, "get_by_email", return_value=local_user),
            patch.object(service.user_repo, "create") as mock_create,
        ):
            result = await service.get_or_create_user(claims)

        assert result is local_user
        assert local_user.role == "tech_lead"
        mock_create.assert_not_called()


class TestAuthenticateSSO:
    """Tests for SSOService.authenticate_sso (full flow)."""

    async def test_full_flow_returns_user(self) -> None:
        mock_session = AsyncMock()
        service = SSOService(mock_session)

        mock_user = _make_mock_user()
        token_response = {"id_token": "valid.id.token", "access_token": "ms-at"}
        claims = {"oid": "oid-full", "email": "user@co.com", "name": "Full Flow"}

        with (
            patch.object(
                service, "exchange_code_for_tokens", return_value=token_response
            ),
            patch.object(service, "validate_id_token", return_value=claims),
            patch.object(service, "get_or_create_user", return_value=mock_user),
        ):
            result = await service.authenticate_sso(
                code="auth-code",
                code_verifier="verifier",
                redirect_uri="http://localhost/callback",
            )

        assert result == mock_user

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
        unverified = {
            "tid": "tenant-x",
            "iss": "https://login.microsoftonline.com/tenant-x/v2.0",
            "preferred_username": "someone@other.example",
        }

        def fake_decode(token: str, *args: object, **kwargs: object) -> dict:
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
