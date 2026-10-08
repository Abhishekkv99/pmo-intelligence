import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Placement } from "@/types/register";

const saveRecord = vi.fn();

vi.mock("@/hooks/useRegister", () => ({
  saveRecord: (...args: unknown[]) => saveRecord(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

import { ApiError } from "@/lib/api";
import { PlacementDialog } from "./PlacementDialog";

const placement: Placement = {
  id: "p1",
  consultant: { id: "c1", full_name: "Vibin Cholayil", email: null },
  client: { id: "cl1", name: "Barclays" },
  project: { id: "pr1", name: "Payments" },
  start_date: "2026-08-17",
  expected_end_date: "2027-02-17",
  extension_status: "not_due",
  rate_band: null,
  status: "active",
  ended_reason: null,
  ps: null,
  sme: null,
  tech_lead: null,
  created_at: "2026-10-08T00:00:00Z",
  updated_at: "2026-10-08T00:00:00Z",
};

function renderDialog() {
  const onSaved = vi.fn();
  const onClose = vi.fn();
  render(
    <PlacementDialog
      placement={placement}
      consultants={[]}
      projects={[]}
      users={[]}
      onClose={onClose}
      onSaved={onSaved}
    />,
  );
  return { onSaved, onClose };
}

describe("PlacementDialog", () => {
  beforeEach(() => saveRecord.mockReset());

  it("refuses an end date before the start", async () => {
    renderDialog();
    // One change event: typing a date key by key is slow under a full run
    fireEvent.change(screen.getByLabelText("Expected end date"), {
      target: { value: "2026-01-01" },
    });

    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Must not be before the start date"),
    ).toBeInTheDocument();
    expect(saveRecord).not.toHaveBeenCalled();
  });

  it("sends every field, with empties as null", async () => {
    saveRecord.mockResolvedValueOnce({});
    const { onSaved, onClose } = renderDialog();

    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
    expect(saveRecord).toHaveBeenCalledWith("/placements", "p1", {
      consultant_id: "c1",
      project_id: "pr1",
      start_date: "2026-08-17",
      expected_end_date: "2027-02-17",
      extension_status: "not_due",
      status: "active",
      rate_band: null,
      ps_user_id: null,
      sme_user_id: null,
      ended_reason: null,
    });
  });

  it("stays open and shows the message from a failed save", async () => {
    saveRecord.mockRejectedValueOnce(
      new ApiError(
        "This consultant already has a placement on this project starting that day",
        409,
      ),
    );
    const { onClose } = renderDialog();

    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "already has a placement",
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
