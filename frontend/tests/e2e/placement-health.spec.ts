import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { test, expect } from "@playwright/test";

/**
 * The placement health page against the real backend. The backend's
 * development-only seed writes an analysed call dated around today (a client
 * dissatisfaction signal, a contract ending in 20 days, an action due in
 * 2 days) and recomputes the placement's health, so the page reads a real
 * snapshot, real flags and real evidence through the API.
 */
interface Seeded {
  session_id: string;
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

test("shows a placement's scores, chart, flags, evidence, call, issue and action", async ({
  page,
}) => {
  const seeded = seedHealth(`${run}p`);

  await page.goto(`/placements/${seeded.placement_id}`);

  await expect(
    page.getByRole("heading", { name: seeded.consultant }),
  ).toBeVisible({ timeout: 15_000 });
  // An open critical flag keeps the placement at least amber.
  await expect(page.getByTestId("health-badge")).toContainText("Amber");
  const tiles = page.getByTestId("score-tile");
  await expect(tiles).toHaveCount(6);
  // A severity 3 client signal three days old pulls Delivery below 5.
  await expect(tiles.filter({ hasText: "Delivery" })).toContainText("Red");
  await expect(tiles.filter({ hasText: "Relationship" })).toContainText(
    "Green",
  );
  await expect(page.getByTestId("health-chart").locator("svg")).toBeVisible();

  const flags = page.getByTestId("flag");
  await expect(flags).toHaveCount(2);
  await expect(flags.nth(0)).toContainText("Client dissatisfaction");
  await expect(flags.nth(0)).toContainText(
    "the client is not happy with the pace",
  );
  await expect(flags.nth(1)).toContainText("Contract horizon");
  await expect(flags.nth(1)).toContainText(
    "Raised from the placement's register",
  );

  await expect(page.getByTestId("contributors").first()).toContainText(
    "weight",
  );
  await expect(page.getByTestId("call")).toHaveCount(1);
  await expect(page.getByTestId("call")).toContainText("Technical help");
  await expect(page.getByTestId("issue")).toContainText(
    "VPN access to the client network",
  );
  await expect(page.getByTestId("action")).toContainText(
    "Chase the client's IT team for VPN access",
  );
  await expect(page.getByTestId("action")).not.toContainText("Overdue");
  await expect(page.getByTestId("register-fields")).toContainText("Dana Lee");
  await expect(page.getByTestId("register-fields")).toContainText("due");
});

test("opens the page from the board, and a missing placement is not found", async ({
  page,
}) => {
  const seeded = seedHealth(`${run}q`);

  await page.goto("/");
  await page.getByLabel("Search placements").fill(seeded.consultant);
  const link = page.getByRole("link", { name: seeded.consultant });
  await expect(link).toHaveCount(1, { timeout: 15_000 });
  await link.click();

  await expect(page).toHaveURL(
    new RegExp(`/placements/${seeded.placement_id}$`),
  );
  await expect(
    page.getByRole("heading", { name: seeded.consultant }),
  ).toBeVisible();

  await page.goto(`/placements/${randomUUID()}`);
  await expect(page.getByText("Placement not found")).toBeVisible({
    timeout: 15_000,
  });
});
