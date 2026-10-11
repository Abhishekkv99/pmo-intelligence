import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { QuickAddResult } from "@/types/register";

const quickAdd = vi.fn();
const mutate = vi.fn();

vi.mock("@/hooks/useRegister", () => ({
  quickAdd: (...args: unknown[]) => quickAdd(...args),
}));
vi.mock("swr", () => ({ useSWRConfig: () => ({ mutate }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

import { ApiError } from "@/lib/api";
import { QuickAddCard } from "./QuickAddCard";

const LINE = "PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027";

function result(overrides: Partial<QuickAddResult> = {}): QuickAddResult {
  return {
    dry_run: true,
    applied: false,
    summary: { lines: 1, created: 1, updated: 0, unchanged: 0, errors: 0 },
    lines: [
      {
        line: 1,
        text: LINE,
        outcome: "create",
        stack: "DS",
        consultant: "Zeeshan Abbas Jaffar",
        client: "WTW",
        start_date: "2026-09-21",
        expected_end_date: "2027-03-21",
        changes: ["client WTW: created"],
        errors: [],
      },
    ],
    ...overrides,
  };
}

async function typeLine(text: string) {
  // Paste rather than type: one change event keeps the test fast
  const box = screen.getByLabelText("Quick add lines");
  await userEvent.click(box);
  await userEvent.paste(text);
}

describe("QuickAddCard", () => {
  beforeEach(() => {
    quickAdd.mockReset();
    mutate.mockReset();
  });

  it("previews before it can confirm", async () => {
    quickAdd.mockResolvedValueOnce(result());
    render(<QuickAddCard />);

    expect(screen.getByRole("button", { name: /Preview/ })).toBeDisabled();
    await typeLine(LINE);
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(quickAdd).toHaveBeenCalledWith([LINE], true);
    expect(await screen.findByTestId("quick-add-summary")).toHaveTextContent(
      "Preview, nothing written yet. 1 lines: 1 new",
    );
    expect(screen.getByText("Zeeshan Abbas Jaffar")).toBeInTheDocument();
    expect(screen.getByText(/WTW · DS · 2026-09-21/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("confirms, clears the box and refreshes the register", async () => {
    quickAdd
      .mockResolvedValueOnce(result())
      .mockResolvedValueOnce(result({ dry_run: false, applied: true }));
    render(<QuickAddCard />);
    await typeLine(LINE);
    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));
    await screen.findByTestId("quick-add-summary");

    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(quickAdd).toHaveBeenLastCalledWith([LINE], false);
    expect(await screen.findByText(/^Saved\./)).toBeInTheDocument();
    expect(screen.getByLabelText("Quick add lines")).toHaveValue("");
    expect(mutate).toHaveBeenCalledWith("/placements");
    expect(mutate).toHaveBeenCalledWith("/projects");
  });

  it("keeps Confirm off while a line has an error", async () => {
    quickAdd.mockResolvedValueOnce(
      result({
        summary: { lines: 1, created: 0, updated: 0, unchanged: 0, errors: 1 },
        lines: [
          {
            line: 1,
            text: "PRJ ITC DS - Zeeshan",
            outcome: "error",
            stack: null,
            consultant: null,
            client: null,
            start_date: null,
            expected_end_date: null,
            changes: [],
            errors: ["expected 5 parts separated by ' - ', found 2"],
          },
        ],
      }),
    );
    render(<QuickAddCard />);
    await typeLine("PRJ ITC DS - Zeeshan");

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(
      await screen.findByText("expected 5 parts separated by ' - ', found 2"),
    ).toBeInTheDocument();
    // The line that could not be read is shown as sent
    expect(
      within(screen.getByRole("table")).getByText("PRJ ITC DS - Zeeshan"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });

  it("shows the message of a refused request", async () => {
    quickAdd.mockRejectedValueOnce(
      new ApiError("Paste at least one line", 422),
    );
    render(<QuickAddCard />);
    await typeLine(LINE);

    await userEvent.click(screen.getByRole("button", { name: /Preview/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Paste at least one line",
    );
  });
});
