import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";

/**
 * The risk board against the real backend. The backend's development-only
 * seed writes an analysed call dated around today (a client dissatisfaction
 * signal, a contract ending in 20 days, an action due in 2 days) and
 * recomputes the placement's health, so the board reads a real snapshot and
 * real flags through the API.
 */
interface Seeded {
  placement_id: string;
  consultant: string;
}

function seedHealth(run: string): Seeded {
  // The compose file is at the repository root, one level above frontend/.
  const out = execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "python",
      "-m",
      "app.cli.seed_e2e_session",
      "--run",
      run,
      "--health",
    ],
    { cwd: "..", encoding: "utf-8" },
  );
  return JSON.parse(out.trim().split("\n").pop() ?? "{}") as Seeded;
}

const run = Date.now().toString(36);

test("shows a placement's health, flags, last call and next action", async ({
  page,
}) => {
  const seeded = seedHealth(`${run}h`);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Risk board" })).toBeVisible();
  await page.getByLabel("Search placements").fill(seeded.consultant);

  const row = page.getByRole("row").filter({ hasText: seeded.consultant });
  await expect(row).toHaveCount(1, { timeout: 15_000 });
  // An open critical flag keeps the placement at least amber.
  await expect(row.getByTestId("health-badge")).toContainText("Amber");
  await expect(row.getByTestId("flag")).toHaveText([
    "Client dissatisfaction",
    "Contract horizon",
  ]);
  await expect(row).toContainText("3 days ago");
  await expect(row).toContainText("Chase the client's IT team for VPN access");
  await expect(row).not.toContainText("overdue");
  // The board groups placements by level; this one is in the Amber section.
  await expect(
    page.getByRole("region", { name: "Amber" }).getByRole("row", {
      name: new RegExp(seeded.consultant),
    }),
  ).toHaveCount(1);
});

test("filters the board by risk level", async ({ page }) => {
  const seeded = seedHealth(`${run}i`);

  await page.goto("/");
  await page.getByLabel("Search placements").fill(seeded.consultant);
  const row = page.getByRole("row").filter({ hasText: seeded.consultant });
  await expect(row).toHaveCount(1, { timeout: 15_000 });

  await page.getByRole("combobox", { name: "Risk level filter" }).click();
  await page.getByRole("option", { name: "Red", exact: true }).click();
  await expect(row).toHaveCount(0);

  await page.getByRole("combobox", { name: "Risk level filter" }).click();
  await page.getByRole("option", { name: "Amber", exact: true }).click();
  await expect(row).toHaveCount(1);

  // The level counts filter the same way; a second click clears it.
  await page.getByRole("combobox", { name: "Risk level filter" }).click();
  await page.getByRole("option", { name: "All levels" }).click();
  const greenCount = page
    .getByTestId("level-count")
    .filter({ hasText: "Green" });
  await greenCount.click();
  await expect(greenCount).toHaveAttribute("aria-pressed", "true");
  await expect(row).toHaveCount(0);
  await greenCount.click();
  await expect(row).toHaveCount(1);
});
