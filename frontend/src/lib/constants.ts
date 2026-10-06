export const APP_NAME = "PMO Intelligence";
export const APP_TAGLINE = "Live health for every consultant placement";

export const ROUTES = {
  home: "/",
  login: "/login",
  actions: "/actions",
  admin: "/admin",
  settings: "/settings",
  ssoCallback: "/auth/callback/microsoft",
} as const;

export const API_ROUTES = {
  health: "/health",
  authLogin: "/auth/login",
  authRefresh: "/auth/refresh",
  authLogout: "/auth/logout",
  authMe: "/auth/me",
  ssoMicrosoftConfig: "/auth/sso/microsoft/config",
  ssoMicrosoftCallback: "/auth/sso/microsoft/callback",
  processingStatus: "/processing/status",
} as const;
