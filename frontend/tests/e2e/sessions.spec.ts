import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";

/**
 * The sessions list and the session page against the real backend. The
 * compose stack cannot transcribe or analyse (no AssemblyAI or Azure OpenAI
 * key), so the backend's development-only seed command writes what an
 * analysed call leaves behind; the page then reads it through the real API.
 */
interface Seeded {
  session_id: string;
  placement_id: string;
  consultant: string;
}

function seed(run: string, failed = false): Seeded {
  const args = [
    "compose",
    "exec",
    "-T",
    "backend",
    "python",
    "-m",
    "app.cli.seed_e2e_session",
    "--run",
    run,
  ];
  if (failed) args.push("--failed");
  // The compose file is at the repository root, one level above frontend/.
  const out = execFileSync("docker", args, { cwd: "..", encoding: "utf-8" });
  return JSON.parse(out.trim().split("\n").pop() ?? "{}") as Seeded;
}

const run = Date.now().toString(36);

test("shows an analysed session with its evidence and recording", async ({
  page,
}) => {
  const seeded = seed(`${run}a`);

  await page.goto(`/sessions/${seeded.session_id}`);

  await expect(
    page.getByRole("heading", { name: seeded.consultant }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByText(/still blocked on VPN access/).first(),
  ).toBeVisible();
  await expect(page.getByTestId("signal")).toHaveCount(2);
  await expect(page.getByTestId("issue")).toContainText(
    "VPN access to the client network",
  );
  await expect(page.getByTestId("action")).toContainText(
    "Chase the client's IT team",
  );
  await expect(page.getByTestId("session-cost")).toContainText("$0.09");
  await expect(page.getByText("Sam (PMO SME)").first()).toBeVisible();
  // The transcript sits in its own column, each line under its speaker.
  await expect(page.getByTestId("transcript")).toContainText("Sam (PMO SME)");
  // The e2e user is a PMO manager, so the failed analysis step shows.
  await expect(page.getByTestId("node-errors")).toContainText(
    "Timed out after 240 s",
  );

  // The player's source is the token-scoped media route, readable without
  // the Bearer token, with Range support.
  const audio = page.getByTestId("session-audio");
  await expect(audio).toHaveAttribute("src", /\/media\?token=/);
  // The seeded recording is real audio: the browser reads its metadata, so
  // the player keeps its element instead of giving up on a decode error.
  await expect
    .poll(() => audio.evaluate((a: HTMLAudioElement) => a.readyState), {
      timeout: 15_000,
    })
    .toBeGreaterThanOrEqual(1);
  const src = (await audio.getAttribute("src")) ?? "";
  const media = await page.request.get(src, {
    headers: { Range: "bytes=0-3" },
  });
  expect(media.status()).toBe(206);
  expect(media.headers()["content-type"]).toBe("audio/webm");
});

test("lists the session and opens it", async ({ page }) => {
  const seeded = seed(`${run}b`);

  await page.goto("/sessions");
  await page.getByLabel("Search sessions").fill(seeded.consultant);
  const link = page.getByRole("link", { name: /1 Oct 2026, 10:00/ });
  await expect(link).toHaveCount(1, { timeout: 15_000 });
  await link.click();

  await expect(page).toHaveURL(new RegExp(`/sessions/${seeded.session_id}$`));
  await expect(
    page.getByRole("heading", { name: seeded.consultant }),
  ).toBeVisible();
});

test("retries a failed session and follows it until it settles", async ({
  page,
}) => {
  // The seed, the page and a real job on a cold stack: the waits below add
  // up to more than the default 30 s, so the test gets room for all of them.
  test.setTimeout(90_000);
  const seeded = seed(`${run}c`, true);

  await page.goto(`/sessions/${seeded.session_id}`);
  await expect(page.getByTestId("session-error")).toContainText(
    "Seeded failure",
    {
      timeout: 15_000,
    },
  );

  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Queued again")).toBeVisible();

  // The job runs for real and fails at transcription (no AssemblyAI key on
  // this stack); the page picks the new outcome up without a reload.
  await expect(page.getByTestId("session-error")).not.toContainText(
    "Seeded failure",
    {
      timeout: 30_000,
    },
  );
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible({
    timeout: 30_000,
  });
});
