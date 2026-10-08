import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ImportResult } from "@/types/register";

const importRegister = vi.fn();

vi.mock("@/hooks/useRegister", () => ({
  importRegister: (...args: unknown[]) => importRegister(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

import { ApiError } from "@/lib/api";
import { ImportTab } from "./ImportTab";

function result(overrides: Partial<ImportResult> = {}): ImportResult {
  return {
    dry_run: true,
    applied: false,
    summary: { rows: 1, created: 1, updated: 0, unchanged: 0, errors: 0 },
    rows: [
      {
        row: 2,
        outcome: "create",
        consultant: "Vibin Cholayil",
        client: "Barclays",
        project: "Payments",
        changes: ["client Barclays: created"],
        warnings: [],
        errors: [],
      },
    ],
    ...overrides,
  };
}

async function chooseFile() {
  const file = new File(["x"], "register.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("CSV file"), file);
  return file;
}

describe("ImportTab", () => {
  beforeEach(() => importRegister.mockReset());

  it("previews, then confirms a clean file", async () => {
    importRegister
      .mockResolvedValueOnce(result())
      .mockResolvedValueOnce(result({ dry_run: false, applied: true }));
    render(<ImportTab />);
    const file = await chooseFile();
    const confirm = screen.getByRole("button", { name: "Confirm import" });
    expect(confirm).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(importRegister).toHaveBeenLastCalledWith(file, true);
    expect(
      await screen.findByText("client Barclays: created"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("import-summary")).toHaveTextContent(
      "Preview, nothing written yet.",
    );

    await userEvent.click(confirm);

    expect(importRegister).toHaveBeenLastCalledWith(file, false);
    await waitFor(() =>
      expect(screen.getByTestId("import-summary")).toHaveTextContent(
        "Imported.",
      ),
    );
  });

  it("keeps Confirm disabled while any row has an error", async () => {
    importRegister.mockResolvedValueOnce(
      result({
        summary: { rows: 1, created: 0, updated: 0, unchanged: 0, errors: 1 },
        rows: [
          {
            ...result().rows[0],
            outcome: "error",
            changes: [],
            errors: ["start_date is required"],
          },
        ],
      }),
    );
    render(<ImportTab />);
    await chooseFile();

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(
      await screen.findByText("start_date is required"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirm import" }),
    ).toBeDisabled();
  });

  it("shows the reason a file was refused", async () => {
    importRegister.mockRejectedValueOnce(
      new ApiError("missing columns: rate_band", 422),
    );
    render(<ImportTab />);
    await chooseFile();

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "missing columns: rate_band",
    );
  });
});
