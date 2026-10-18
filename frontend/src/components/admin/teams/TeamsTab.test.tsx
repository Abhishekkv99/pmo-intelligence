import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import type { QuickAddResult } from "@/types/register";
import type { TeamsChat, TeamsChatList } from "@/types/teams";

const mutate = vi.fn();
const requestTeamsScan = vi.fn();
const chooseChatPlacement = vi.fn();
const createChatPlacement = vi.fn();
const chooseConsultantMember = vi.fn();
const success = vi.fn();
let list: TeamsChatList | null = null;

vi.mock("@/hooks/useTeamsChats", () => ({
  useTeamsChats: () => ({ list, isLoading: false, error: null, mutate }),
  requestTeamsScan: () => requestTeamsScan(),
  chooseChatPlacement: (...args: unknown[]) => chooseChatPlacement(...args),
  createChatPlacement: (...args: unknown[]) => createChatPlacement(...args),
  chooseConsultantMember: (...args: unknown[]) =>
    chooseConsultantMember(...args),
}));
vi.mock("@/hooks/useRegister", () => ({
  usePlacements: () => ({ items: [] }),
}));
vi.mock("sonner", () => ({
  toast: { success: (m: string) => success(m), error: vi.fn() },
}));

import { TeamsTab } from "./TeamsTab";

const alexPlacement = {
  id: "p1",
  consultant_name: "Alex Sample",
  client_name: "Demo Client",
  project_name: "Payments",
  start_date: "2026-09-21",
  expected_end_date: "2027-03-21",
  status: "active" as const,
};
const otherPlacement = {
  ...alexPlacement,
  id: "p2",
  consultant_name: "Alex Other",
};

function chat(overrides: Partial<TeamsChat>): TeamsChat {
  return {
    id: "c0",
    title: "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027",
    parsed: {
      stack: "DS",
      consultant: "Alex Sample",
      client: "Demo Client",
      start_date: "2026-09-21",
      end_date: "2027-03-21",
    },
    quick_add_line:
      "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027",
    match_status: "matched",
    placement: alexPlacement,
    candidates: [],
    watch_state: "watching",
    watched_at: "2026-10-18T09:00:00Z",
    stopped_at: null,
    members: [
      { oid: "o1", name: "Alex Sample" },
      { oid: "o2", name: "Pat Manager" },
    ],
    consultant_member: { oid: "o1", name: "Alex Sample" },
    consultant_member_match: "matched",
    last_message_at: null,
    history_state: "none",
    error_message: null,
    ...overrides,
  };
}

const watched = chat({ id: "c1" });
const several = chat({
  id: "c2",
  title: "PRJ ITC DS - Alex - Demo Client - 21/9/2026 - 21/3/2027",
  match_status: "needs_choice",
  placement: null,
  candidates: [alexPlacement, otherPlacement],
  watch_state: "not_watched",
  watched_at: null,
  members: [],
  consultant_member: null,
  consultant_member_match: "unmatched",
});
const unread = chat({
  id: "c3",
  title: "PRJ ITC - team social",
  parsed: null,
  quick_add_line: "PRJ ITC - team social",
  match_status: "unparsed",
  placement: null,
  watch_state: "not_watched",
  watched_at: null,
  members: [],
  consultant_member: null,
  consultant_member_match: "unmatched",
  error_message: "Title not read: expected a start and an end date",
});
const unclearMember = chat({
  id: "c4",
  title: "PRJ ITC QA - Sam Other - Demo Client - 5/10/2026 - 5/4/2027",
  placement: { ...alexPlacement, id: "p3", consultant_name: "Sam Other" },
  consultant_member: null,
  consultant_member_match: "needs_choice",
  members: [
    { oid: "o3", name: "Sam Other" },
    { oid: "o4", name: "Sam Third" },
  ],
});

function setList(chats: TeamsChat[], overrides: Partial<TeamsChatList> = {}) {
  list = {
    chats,
    latest_scan: {
      id: "s1",
      started_at: "2026-10-18T09:00:00Z",
      finished_at: "2026-10-18T09:01:00Z",
      status: "completed",
      chats_seen: chats.length,
      chats_added: 1,
      chats_matched: 2,
      error_message: null,
    },
    discovery_enabled: true,
    watching_enabled: true,
    ...overrides,
  };
}

function waitingCard() {
  return screen
    .getByText(/Chats waiting for a person/)
    .closest("[data-slot=card]") as HTMLElement;
}

describe("TeamsTab", () => {
  beforeAll(() => {
    // Radix Select uses pointer capture and scrolling, which jsdom lacks.
    Element.prototype.hasPointerCapture = vi.fn(() => false);
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    setList([watched, several, unread, unclearMember]);
  });

  it("shows the last discovery and every chat in the table", () => {
    render(<TeamsTab enabled />);

    expect(
      screen.getByText(/4 chats \(1 new, 2 matched\)\. Discovery runs daily\./),
    ).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    expect(within(table).getAllByText("Watching").length).toBeGreaterThan(0);
    expect(within(table).getByText("Title not read")).toBeInTheDocument();
  });

  it("lists the chats waiting for a person, placements first", () => {
    render(<TeamsTab enabled />);

    const card = waitingCard();
    expect(card).toHaveTextContent("Chats waiting for a person (3)");
    const titles = within(card)
      .getAllByText(/^PRJ ITC/)
      .map((el) => el.textContent);
    expect(titles).toEqual([several.title, unread.title, unclearMember.title]);
    expect(card).toHaveTextContent(
      "Could be Alex Sample at Demo Client or Alex Other at Demo Client",
    );
    expect(card).toHaveTextContent(
      "Title not read: expected a start and an end date",
    );
    expect(card).toHaveTextContent(
      "Several members could be the consultant (Sam Other)",
    );
  });

  it("hides the card when nothing waits", () => {
    setList([watched]);
    render(<TeamsTab enabled />);

    expect(screen.queryByText(/Chats waiting for a person/)).toBeNull();
  });

  it("filters the table by match state", async () => {
    const user = userEvent.setup();
    render(<TeamsTab enabled />);

    await user.click(screen.getByRole("combobox", { name: "Match filter" }));
    await user.click(screen.getByRole("option", { name: "Title not read" }));

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText(unread.title)).toBeInTheDocument();
  });

  it("creates the placement from the title with the prefilled line", async () => {
    const user = userEvent.setup();
    const applied: QuickAddResult = {
      dry_run: false,
      applied: true,
      summary: { lines: 1, created: 1, updated: 0, unchanged: 0, errors: 0 },
      lines: [],
    };
    createChatPlacement.mockResolvedValue(applied);
    render(<TeamsTab enabled />);

    const card = waitingCard();
    await user.click(
      within(card).getAllByRole("button", { name: "Create from title" })[0],
    );
    const line = screen.getByLabelText("Quick add line");
    expect(line).toHaveValue(several.quick_add_line);
    await user.click(screen.getByRole("button", { name: "Create and link" }));

    expect(createChatPlacement).toHaveBeenCalledWith(
      "c2",
      several.quick_add_line,
    );
    expect(success).toHaveBeenCalledWith("Placement written and chat linked");
    expect(mutate).toHaveBeenCalled();
  });

  it("shows the line's errors when the quick add writes nothing", async () => {
    const user = userEvent.setup();
    createChatPlacement.mockResolvedValue({
      dry_run: false,
      applied: false,
      summary: { lines: 1, created: 0, updated: 0, unchanged: 0, errors: 1 },
      lines: [
        {
          line: 1,
          text: "x",
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
    } satisfies QuickAddResult);
    render(<TeamsTab enabled />);

    await user.click(
      within(waitingCard()).getAllByRole("button", {
        name: "Create from title",
      })[1],
    );
    await user.click(screen.getByRole("button", { name: "Create and link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "expected 5 parts separated by ' - ', found 2",
    );
    expect(mutate).not.toHaveBeenCalled();
  });

  it("chooses a candidate placement for a chat", async () => {
    const user = userEvent.setup();
    chooseChatPlacement.mockResolvedValue(undefined);
    render(<TeamsTab enabled />);

    await user.click(
      within(waitingCard()).getByRole("button", { name: "Choose placement" }),
    );
    await user.click(screen.getByRole("combobox", { name: "Placement" }));
    await user.click(
      screen.getByRole("option", { name: /Alex Other .*matches the title/ }),
    );
    await user.click(screen.getByRole("button", { name: "Link" }));

    expect(chooseChatPlacement).toHaveBeenCalledWith("c2", "p2");
    expect(mutate).toHaveBeenCalled();
  });

  it("chooses the consultant among the members", async () => {
    const user = userEvent.setup();
    chooseConsultantMember.mockResolvedValue(undefined);
    render(<TeamsTab enabled />);

    await user.click(
      within(waitingCard()).getByRole("button", { name: "Choose consultant" }),
    );
    await user.click(screen.getByRole("combobox", { name: "Member" }));
    await user.click(screen.getByRole("option", { name: "Sam Other" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(chooseConsultantMember).toHaveBeenCalledWith("c4", "o3");
  });

  it("queues discovery, and cannot while it is off", async () => {
    const user = userEvent.setup();
    requestTeamsScan.mockResolvedValue({ queued: true });
    const { unmount } = render(<TeamsTab enabled />);

    await user.click(screen.getByRole("button", { name: "Scan now" }));
    expect(success).toHaveBeenCalledWith(
      "Discovery queued; new chats appear in a minute or two",
    );
    unmount();

    setList([], { discovery_enabled: false, latest_scan: null });
    render(<TeamsTab enabled />);
    expect(screen.getByRole("button", { name: "Scan now" })).toBeDisabled();
    expect(
      screen.getByText(
        /No discovery yet\. Discovery is off on this environment\./,
      ),
    ).toBeInTheDocument();
  });

  it("says when the last discovery failed and when watching is off", () => {
    setList([], {
      watching_enabled: false,
      latest_scan: {
        id: "s2",
        started_at: "2026-10-18T09:00:00Z",
        finished_at: "2026-10-18T09:00:05Z",
        status: "failed",
        chats_seen: 0,
        chats_added: 0,
        chats_matched: 0,
        error_message: "GraphError: Forbidden",
      },
    });
    render(<TeamsTab enabled />);

    expect(screen.getByText(/Last discovery failed at/)).toHaveTextContent(
      "GraphError: Forbidden",
    );
    expect(screen.getByText(/Watching is off/)).toBeInTheDocument();
  });
});
