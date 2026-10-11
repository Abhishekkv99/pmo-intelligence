import { test, expect } from "@playwright/test";

/**
 * The placement register on the Admin page, against the real backend.
 *
 * The e2e user is a PMO manager (docker-compose.yml lists it in
 * BOOTSTRAP_ADMIN_EMAILS), so it may edit the register. The compose database
 * keeps its data between runs, so every name here carries a run id.
 */
const run = Date.now().toString(36);

test.describe("Admin register", () => {
  test("adds a client through the dialog", async ({ page }) => {
    const name = `Client ${run}`;
    await page.goto("/admin?tab=register");
    await page.getByRole("tab", { name: "Clients" }).click();

    await page.getByRole("button", { name: "Add client" }).click();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Industry").fill("Banking");
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();

    // The same name again is refused, and the dialog says why
    await page.getByRole("button", { name: "Add client" }).click();
    await page.getByLabel("Name").fill(name.toUpperCase());
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("alert")).toContainText("already exists");
  });

  test("previews and saves a quick-add line, then lists the placement", async ({
    page,
  }) => {
    const consultant = `Asha ${run}`;
    const client = `Quick Client ${run}`;
    const line = `PRJ ITC DS - ${consultant} - ${client} - 17/8/2026 - 17/02/2027`;

    await page.goto("/admin?tab=register");
    await page.getByLabel("Quick add lines").fill(line);
    await page.getByRole("button", { name: "Preview" }).click();

    // The first write after a container restart is slow (a cold backend), so
    // these steps get the allowance auth.setup.ts gives the first page.
    const summary = page.getByTestId("quick-add-summary");
    await expect(summary).toContainText("Preview, nothing written yet.", {
      timeout: 15_000,
    });
    await expect(summary).toContainText("1 new");

    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(summary).toContainText("Saved.", { timeout: 15_000 });

    await page.getByLabel("Search placements").fill(consultant);
    // The placements table's row: the quick-add result above it names the
    // consultant too, but has no project cell.
    const row = page
      .getByRole("row")
      .filter({ hasText: consultant })
      .filter({
        has: page.getByRole("cell", { name: "To be confirmed", exact: true }),
      });
    await expect(
      row.getByRole("cell", { name: client, exact: true }),
    ).toBeVisible();
    await expect(
      row.getByRole("cell", { name: "DS", exact: true }),
    ).toBeVisible();
  });
});
