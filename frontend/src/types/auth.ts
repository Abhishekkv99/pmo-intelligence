import type { Role } from "@/lib/roles";

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  auth_provider: "local" | "microsoft_entra";
  /** The entitlement; `null` until a role is granted, and then the user reads nothing. */
  role: Role | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface SSOConfigResponse {
  client_id: string;
  tenant_id: string;
  /** Authority segment for the authorize URL: the tenant ID, or "organizations" when other tenants are allowed. */
  authority: string;
  redirect_uri: string;
}

export interface SSOCallbackRequest {
  code: string;
  code_verifier: string;
  redirect_uri: string;
}
