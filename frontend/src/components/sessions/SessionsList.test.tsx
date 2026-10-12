import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import type { SessionListItem } from "@/types/sessions";

let sessions: SessionListItem[] | null = null;

vi.mock("@/hooks/useSessions", () => ({
  useSessions: () => ({
    sessions,
    isLoading: false,
    error: null,
    mutate: vi.fn(),
  }),
}));

import { SessionsList } from "./SessionsList";

function item(overrides: Partial<SessionListItem>): SessionListItem {
  return {
    id: "s1",
    placement_id: "p1",
    consultant: { id: "c1", name: "Priya Shah" },
    client: { id: "cl1", name: "Acme" },
    project: { id: "pr1", name: "Data platform" },
    held_at: "2026-10-01T09:00:00Z",
    duration_seconds: 1_200,
    kind: "technical",
    status: "completed",
    error_message: null,
    signal_count: 4,
    action_count: 2,
    ...overrides,
  };
}

describe("SessionsList", () => {
  beforeAll(() => {
    // Radix Select uses pointer capture and scrolling, which jsdom lacks.
    Element.prototype.hasPointerCapture = vi.fn(() => false);
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    sessions = [
      item({}),
      item({
        id: "s2",
        consultant: { id: "c2", name: "Ann Brooks" },
        held_at: "2026-09-20T09:00:00Z",
        kind: null,
        status: "failed",
        error_message: "TranscriptionError: no audio",
        duration_seconds: null,
        signal_count: 0,
        action_count: 0,
      }),
    ];
  });

  it("lists each session with a link to its page", () => {
    render(<SessionsList />);

    const link = screen.getByRole("link", { name: "1 Oct 2026, 10:00" });
    expect(link).toHaveAttribute("href", "/sessions/s1");
    const row = link.closest("tr")!;
    // The consultant's name opens the placement page.
    expect(
      within(row).getByRole("link", { name: "Priya Shah" }),
    ).toHaveAttribute("href", "/placements/p1");
    expect(within(row).getByText("Acme · Data platform")).toBeInTheDocument();
    expect(within(row).getByText("Technical help")).toBeInTheDocument();
    expect(within(row).getByText("20 min")).toBeInTheDocument();
  });

  it("shows an unclassified call and a failed one's reason", () => {
    render(<SessionsList />);

    const row = screen
      .getByRole("link", { name: "20 Sept 2026, 10:00" })
      .closest("tr")!;
    expect(within(row).getByText("Not classified")).toBeInTheDocument();
    expect(within(row).getByText("Failed")).toHaveAttribute(
      "title",
      "TranscriptionError: no audio",
    );
    // A failed call's row is tinted; a settled one is not.
    expect(row).toHaveClass("bg-destructive/5");
    expect(
      screen.getByRole("link", { name: "1 Oct 2026, 10:00" }).closest("tr"),
    ).not.toHaveClass("bg-destructive/5");
  });

  it("searches the consultant, client, project, kind and status", async () => {
    const user = userEvent.setup();
    render(<SessionsList />);
    const search = screen.getByLabelText("Search sessions");
    const consultants = () =>
      screen
        .getAllByRole("row")
        .slice(1)
        .map((r) => within(r).getAllByRole("cell")[1].textContent);

    await user.click(search);
    await user.paste("technical help");
    expect(consultants()).toEqual(["Priya Shah"]);

    await user.clear(search);
    await user.click(search);
    await user.paste("failed");
    expect(consultants()).toEqual(["Ann Brooks"]);

    await user.clear(search);
    await user.click(search);
    await user.paste("nothing like this");
    expect(
      screen.getByText("No sessions match these filters."),
    ).toBeInTheDocument();
  });

  it("filters by consultant", async () => {
    const user = userEvent.setup();
    render(<SessionsList />);

    await user.click(
      screen.getByRole("combobox", { name: "Consultant filter" }),
    );
    await user.click(screen.getByRole("option", { name: "Ann Brooks" }));

    expect(screen.queryByText("Priya Shah")).not.toBeInTheDocument();
    expect(screen.getAllByText("Ann Brooks").length).toBeGreaterThan(0);
  });

  it("says so when there are no sessions", () => {
    sessions = [];
    render(<SessionsList />);

    expect(screen.getByText(/No sessions yet/)).toBeInTheDocument();
  });
});
