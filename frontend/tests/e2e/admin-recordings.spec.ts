import { test, expect } from "@playwright/test";

/**
 * Admin > Recordings against the real backend. The compose stack has no
 * access to the recordings bucket and no AssemblyAI key, so the folder list
 * is empty and an uploaded session fails at transcription in the background;
 * what is checked here is the page and the upload path up to the queue.
 */
const run = Date.now().toString(36);
const consultant = `Rhea ${run}`;

// The first bytes of a WebM (Matroska) file, enough for the type check.
const WEBM = Buffer.concat([
  Buffer.from([0x1a, 0x45, 0xdf, 0xa3]),
  Buffer.alloc(2048),
]);

test("uploads a recording for a placement", async ({ page }) => {
  // A placement to upload for, through the register import.
  const csv = [
    "consultant_full_name,consultant_email,client_name,project_name,client_manager_name,tech_lead_email,ps_email,sme_email,start_date,expected_end_date,extension_status,rate_band",
    `${consultant},rhea.${run}@example.com,Recordings Client ${run},Platform,,,,,2026-08-01,,,`,
  ].join("\r\n");
  await page.goto("/admin?tab=import");
  await page.getByLabel("CSV file").setInputFiles({
    name: "register.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page.getByRole("button", { name: "Preview" }).click();
  const summary = page.getByTestId("import-summary");
  await expect(summary).toContainText("1 new", { timeout: 15_000 });
  await page.getByRole("button", { name: "Confirm import" }).click();
  await expect(summary).toContainText("Imported.", { timeout: 15_000 });

  await page.goto("/admin?tab=recordings");
  await expect(page.getByText(/Automatic scan is off/)).toBeVisible();

  await page.getByRole("button", { name: "Upload recording" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Upload" })).toBeDisabled();

  await dialog.getByTestId("file-input").setInputFiles({
    name: "Recording 2026-10-01 10-00-00.webm",
    mimeType: "video/webm",
    buffer: WEBM,
  });
  // The call time is read from the Talk-style name.
  await expect(dialog.getByLabel("When was the call? (UK time)")).toHaveValue(
    "2026-10-01T10:00",
  );

  await dialog.getByLabel("Filter placement").fill(consultant);
  await dialog.getByRole("combobox", { name: "Placement" }).click();
  await page.getByRole("option", { name: new RegExp(consultant) }).click();
  await dialog.getByRole("button", { name: "Upload" }).click();

  await expect(
    page.getByText("Uploaded and queued for transcription"),
  ).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("accepts only https recording URLs", async ({ page }) => {
  await page.goto("/admin?tab=recordings");
  await page.getByRole("button", { name: "Add from URL" }).click();
  const dialog = page.getByRole("dialog");

  await dialog.getByLabel("Recording URL").fill("http://example.com/call.webm");
  await dialog
    .getByLabel("When was the call? (UK time)")
    .fill("2026-10-01T10:00");
  await expect(dialog.getByRole("button", { name: "Add" })).toBeDisabled();
});
