// In-memory token storage — NOT localStorage.
// Token is lost on page refresh and recovered via the httpOnly refresh cookie
// hitting POST /auth/refresh on mount (see AuthProvider).
//
// On init, check for a pre-seeded token in localStorage (used by E2E tests
// to avoid refresh token rotation issues across isolated browser contexts).
// The key is deliberately NOT cleared after reading: a single test can load
// more than one document (a server-side redirect is a fresh page load), and
// consuming the seed on the first load would leave the second with no token,
// forcing it onto the rate-limited refresh endpoint.
let accessToken: string | null = null;
if (typeof window !== "undefined") {
  const seeded = localStorage.getItem("_e2e_token");
  if (seeded) {
    accessToken = seeded;
  }
}

export function getToken(): string | null {
  return accessToken;
}

export function setToken(token: string): void {
  accessToken = token;
}

export function removeToken(): void {
  accessToken = null;
}
