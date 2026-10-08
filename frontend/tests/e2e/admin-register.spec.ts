import { test, expect } from "@playwright/test";

/**
 * The placement register on the Admin page, against the real backend.
 *
 * The e2e user is a PMO manager (docker-compose.yml lists it in
 * BOOTSTRAP_ADMIN_EMAILS), so it may edit the register. The compose database
 * keeps its data between runs, so every name here carries a run id.
 */
const run = Date.now().toString(36);

const COLUMNS = [
  "consultant_full_name",
  "consultant_email",
  "client_name",
  "project_name",
  "client_manager_name",
  "tech_lead_email",
  "ps_email",
  "sme_email",
  "start_date",
  "expected_end_date",
  "extension_status",
  "rate_band",
];

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

  test("previews and imports a CSV, then lists the placement", async ({
    page,
  }) => {
    const consultant = `Asha ${run}`;
    const csv = [
      COLUMNS.join(","),
      [
        consultant,
        `asha.${run}@example.com`,
        `Import Client ${run}`,
        "Payments",
        "",
        "",
        "",
        "",
        "17/08/2026",
        "2027-02-17",
        "",
        "",
      ].join(","),
    ].join("\r\n");

    await page.goto("/admin?tab=import");
    await page.getByLabel("CSV file").setInputFiles({
      name: "register.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await page.getByRole("button", { name: "Preview" }).click();

    const summary = page.getByTestId("import-summary");
    await expect(summary).toContainText("Preview, nothing written yet.");
    await expect(summary).toContainText("1 new");

    await page.getByRole("button", { name: "Confirm import" }).click();
    await expect(summary).toContainText("Imported.");

    await page.getByRole("tab", { name: "Register" }).click();
    await page.getByLabel("Search placements").fill(consultant);
    await expect(page.getByText(consultant, { exact: true })).toBeVisible();
  });
});
