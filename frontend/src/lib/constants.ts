export const APP_NAME = "PMO Intelligence";
export const APP_TAGLINE = "Live health for every consultant placement";

export const ROUTES = {
  home: "/",
  login: "/login",
  actions: "/actions",
  sessions: "/sessions",
  placements: "/placements",
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
  consultants: "/consultants",
  clients: "/clients",
  projects: "/projects",
  placements: "/placements",
  registerImport: "/register/import",
  users: "/users",
  recordingFolders: "/recording-folders",
  recordingsScan: "/recordings/scan",
  recordings: "/recordings",
  sessionUpload: "/sessions/upload",
  sessionUrl: "/sessions/url",
  sessions: "/sessions",
  riskBoard: "/risk-board",
} as const;
