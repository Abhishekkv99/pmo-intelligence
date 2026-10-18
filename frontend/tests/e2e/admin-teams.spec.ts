import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";

/**
 * Admin > Teams against the real backend. The compose stack has no Graph
 * access and discovery is off, so the backend's development-only seed writes
 * what discovery leaves behind for three made-up chats; the page reads them
 * through the real API, and a placement is created from one chat's title.
 */
interface Seeded {
  unmatched: string;
  unparsed: string;
  matched: string;
}

function seed(run: string): Seeded {
  const out = execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "python",
      "-m",
      "app.cli.seed_e2e_teams",
      "--run",
      run,
    ],
    // The compose file is at the repository root, one level above frontend/.
    { cwd: "..", encoding: "utf-8" },
  );
  return JSON.parse(out.trim().split("\n").pop() ?? "{}") as Seeded;
}

const run = Date.now().toString(36);

test("lists the chats and creates a placement from a chat's title", async ({
  page,
}) => {
  const seeded = seed(run);

  await page.goto("/admin?tab=teams");
  await expect(
    page.getByText(/Discovery is off on this environment/),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Scan now" })).toBeDisabled();

  const card = page.locator("[data-slot=card]", {
    hasText: "Chats waiting for a person",
  });
  await expect(card.getByText(seeded.unmatched)).toBeVisible();
  await expect(card.getByText(seeded.unparsed)).toBeVisible();
  await expect(card.getByText(seeded.matched)).toHaveCount(0);

  // The matched chat is in the table with its placement.
  await page.getByLabel("Search chat, consultant, client").fill(`Omar ${run}`);
  const table = page.getByRole("table");
  await expect(table.getByText(seeded.matched)).toBeVisible();
  await expect(table.getByText("Matched")).toBeVisible();
  await page.getByLabel("Search chat, consultant, client").fill("");

  const row = card.getByTestId("waiting-chat").filter({
    hasText: seeded.unmatched,
  });
  await row.getByRole("button", { name: "Create from title" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Quick add line")).toHaveValue(
    `PRJ ITC DS - Nia ${run} - Teams Client ${run} - 21/9/2026 - 21/3/2027`,
  );
  await dialog.getByRole("button", { name: "Create and link" }).click();

  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect(card.getByText(seeded.unmatched)).toHaveCount(0, {
    timeout: 15_000,
  });
  await page.getByLabel("Search chat, consultant, client").fill(`Nia ${run}`);
  await expect(table.getByText(seeded.unmatched)).toBeVisible();
  await expect(table.getByText("Chosen")).toBeVisible();
  await expect(table.getByText(`Nia ${run}`, { exact: true })).toBeVisible();
});
