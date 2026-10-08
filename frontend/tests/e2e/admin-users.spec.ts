import { test, expect } from "@playwright/test";

/**
 * Users and roles on the Admin page, against the real backend. The e2e user
 * is a PMO manager; every address here carries a run id because the compose
 * database keeps its data between runs.
 */
const email = `colleague.${Date.now().toString(36)}@example.com`;

test("gives a colleague access, then takes it away", async ({ page }) => {
  await page.goto("/admin?tab=users");

  await page.getByRole("button", { name: "Give access" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("combobox", { name: "Role" }).click();
  await page.getByRole("option", { name: "PMO SME" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByLabel("Search users").fill(email);
  const row = page.getByRole("row").filter({ hasText: email });
  await expect(row.getByText("PMO SME")).toBeVisible();
  await expect(row.getByText("Not yet")).toBeVisible();

  await row.getByRole("button", { name: /Change the role of/ }).click();
  await page.getByRole("combobox", { name: "Role" }).click();
  await page.getByRole("option", { name: "No role (no access)" }).click();
  await page.getByRole("button", { name: "Save" }).click();

  await expect(row.getByText("No role")).toBeVisible();
});
