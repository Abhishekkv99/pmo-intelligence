import { test as setup, expect } from "@playwright/test";

const authFile = "playwright/.auth/user.json";

/**
 * Authenticate once before all tests.
 *
 * Signs in through the API rather than the login page. The login page offers
 * only the Microsoft button, and an interactive Microsoft sign-in cannot run
 * unattended — so the suite authenticates with a password against a backend
 * started with LOCAL_AUTH_ENABLED=true. Staging and production run with it
 * false, where these two endpoints return 403.
 *
 * Requires E2E_USER_EMAIL and E2E_USER_PASSWORD env vars (defaults provided
 * for local Docker Compose). The user registers with no role (unless it is
 * listed in BOOTSTRAP_ADMIN_EMAILS), so the suite checks only what every
 * signed-in user sees: the risk board, actions and settings.
 */
setup("authenticate", async ({ page, context, request }) => {
  const email =
    process.env.E2E_USER_EMAIL ?? "e2e@informationtechconsultants.com";
  const password = process.env.E2E_USER_PASSWORD ?? "testpassword123";
  const apiUrl = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

  // Ensure the test user exists (idempotent — ignored if already registered).
  await request.post(`${apiUrl}/auth/register`, {
    data: { email, password, full_name: "Test User" },
  });

  const loginResponse = await request.post(`${apiUrl}/auth/login`, {
    data: { email, password },
  });
  expect(
    loginResponse.ok(),
    `Login failed with ${loginResponse.status()}. A 403 means the backend was ` +
      `started with LOCAL_AUTH_ENABLED=false; the E2E suite needs it true.`,
  ).toBeTruthy();
  const { access_token } = (await loginResponse.json()) as {
    access_token: string;
  };

  // The refresh cookie was set on the API request context, so copy it into the
  // browser context. Cookies are scoped by domain and path but not by port, so
  // the cookie issued by the backend on :8000 is sent by the page on :3000.
  const { cookies } = await request.storageState();
  await context.addCookies(cookies);

  // Confirm the cookie alone authenticates. The app restores the session on
  // mount via /auth/refresh, exactly as it does after a Microsoft sign-in.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Risk board" })).toBeVisible({
    timeout: 15_000,
  });

  // Seed the access token into localStorage so subsequent test contexts can use
  // it directly without needing to refresh (which rotates the httpOnly refresh
  // cookie and breaks other contexts sharing the same storageState, and is rate
  // limited to 10/min besides). auth-token reads the key on every page load and
  // leaves it in place, so it survives a test that loads more than one document.
  await page.evaluate(
    (token) => localStorage.setItem("_e2e_token", token),
    access_token,
  );

  await context.storageState({ path: authFile });
});
