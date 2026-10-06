import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutResponse(BaseModel):
    message: str
    revoked_tokens: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    auth_provider: str = "local"
    # The entitlement; None until a role is granted (the user reads nothing).
    role: Role | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SSOConfigResponse(BaseModel):
    client_id: str
    tenant_id: str
    # The path segment the frontend puts after login.microsoftonline.com in
    # the authorize URL: the tenant ID while single-tenant, "organizations"
    # once other tenants are allowed.
    authority: str
    redirect_uri: str


class SSOCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    code_verifier: str = Field(..., min_length=43, max_length=128)
    redirect_uri: str = Field(..., min_length=1)
