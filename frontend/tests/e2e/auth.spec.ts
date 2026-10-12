import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test.describe("login page (unauthenticated)", () => {
    test.use({ storageState: { cookies: [], origins: [] } });

    test("offers only Microsoft sign-in", async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");

      // CardTitle renders as <div data-slot="card-title"> in shadcn v4
      await expect(page.locator("[data-slot='card-title']")).toContainText(
        "Sign In",
      );
      await expect(
        page.getByRole("button", { name: /sign in with microsoft/i }),
      ).toBeVisible();
    });

    test("exposes no password sign-in on the page", async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");

      // Microsoft is the only way in — these must not come back via a stale
      // import or a partially reverted change.
      await expect(page.locator("#email")).toHaveCount(0);
      await expect(page.locator("#password")).toHaveCount(0);
      await expect(page.getByRole("link", { name: /sign up/i })).toHaveCount(0);
    });

    test("sends a signup attempt back to the login page", async ({ page }) => {
      // The route is gone, but an unauthenticated visitor never reaches Next's
      // 404 — the proxy guard redirects every non-public path to /login first.
      // The 404 itself is asserted below, from an authenticated context.
      await page.goto("/signup");
      await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    });
  });

  test("no longer serves a signup route", async ({ page }) => {
    // Authenticated, so the proxy passes the request through to Next's router
    // and a missing route surfaces as a real 404 rather than a login redirect.
    const response = await page.goto("/signup");
    expect(response?.status()).toBe(404);
  });

  test("authenticated user lands on the risk board", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { name: "Risk board" }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Actions" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
  });

  test("authenticated user is sent from the login page to the risk board", async ({
    page,
  }) => {
    await page.goto("/login");

    await expect(page).toHaveURL(/\/$/, { timeout: 10_000 });
    await expect(
      page.getByRole("heading", { name: "Risk board" }),
    ).toBeVisible();
  });

  test("authenticated user can open the actions page", async ({ page }) => {
    await page.goto("/actions");

    await expect(
      page.getByRole("heading", { name: "Actions", exact: true }),
    ).toBeVisible();
  });

  test("authenticated user sees the shell: logo link and section breadcrumb", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(
      page.getByRole("link", { name: "PMO Intelligence" }),
    ).toHaveAttribute("href", "/");
    await expect(
      page
        .getByRole("navigation", { name: "breadcrumb" })
        .getByText("Risk board"),
    ).toBeVisible();
  });

  test("the sidebar collapses to an icon rail and stays so on reload", async ({
    page,
  }) => {
    await page.goto("/");
    const sidebar = page.locator("[data-slot='sidebar'][data-state]");
    await expect(sidebar).toHaveAttribute("data-state", "expanded");

    await page.getByRole("button", { name: "Toggle Sidebar" }).first().click();
    await expect(sidebar).toHaveAttribute("data-state", "collapsed");

    await page.reload();
    await expect(sidebar).toHaveAttribute("data-state", "collapsed");
    await page.getByRole("button", { name: "Toggle Sidebar" }).first().click();
    await expect(sidebar).toHaveAttribute("data-state", "expanded");
  });

  test("on a phone the sidebar is a drawer that a link closes", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    await expect(page.getByRole("link", { name: "Sessions" })).toBeHidden();
    await page.getByRole("button", { name: "Toggle Sidebar" }).click();
    const drawer = page.getByRole("dialog");
    await drawer.getByRole("link", { name: "Sessions" }).click();

    await expect(page).toHaveURL(/\/sessions$/);
    await expect(drawer).toBeHidden();
  });
});
