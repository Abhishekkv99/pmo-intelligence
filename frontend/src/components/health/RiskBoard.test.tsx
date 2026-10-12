import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest";
import type { RiskBoardRow } from "@/types/health";

let rows: RiskBoardRow[] | null = null;
let role: string = "pmo_manager";

vi.mock("@/hooks/useHealth", () => ({
  useRiskBoard: () => ({
    rows,
    isLoading: false,
    error: null,
    mutate: vi.fn(),
  }),
}));
vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { role } }),
}));

import { RiskBoard } from "./RiskBoard";

function row(overrides: Partial<RiskBoardRow>): RiskBoardRow {
  return {
    placement_id: "p1",
    view: "full",
    consultant: { id: "c1", name: "Priya Shah" },
    client: { id: "cl1", name: "Acme" },
    project: { id: "pr1", name: "Data platform" },
    ps: { id: "u1", full_name: "Pat Jones", email: "pat@x.com" },
    cdm: { id: "u2", full_name: "Lee Tan", email: "lee@x.com" },
    stack: "DS",
    start_date: "2026-09-01",
    weeks_in: 7,
    scored: true,
    computed_at: "2026-10-20T12:00:00Z",
    overall: 4.6,
    risk_level: "red",
    trend: "down",
    trend_delta: -1.2,
    technical: 6.1,
    technical_trend: "flat",
    technical_trend_delta: 0.2,
    open_flags: [
      {
        id: "f1",
        trigger: "client_dissatisfaction",
        severity: "critical",
        opened_at: "2026-10-18T12:00:00Z",
      },
      {
        id: "f2",
        trigger: "contract_horizon",
        severity: "high",
        opened_at: "2026-10-18T12:00:00Z",
      },
    ],
    last_call_at: "2026-10-15T09:00:00Z",
    days_since_last_call: 5,
    next_action: {
      id: "a1",
      description: "Send the report",
      owner_role: "consultant",
      due_date: "2026-10-18",
    },
    ...overrides,
  };
}

const UNSCORED: Partial<RiskBoardRow> = {
  placement_id: "p2",
  consultant: { id: "c2", name: "Ann Brooks" },
  client: { id: "cl2", name: "Globex" },
  ps: null,
  cdm: null,
  stack: "BD",
  scored: false,
  computed_at: null,
  overall: null,
  risk_level: null,
  trend: null,
  trend_delta: null,
  technical: null,
  technical_trend: null,
  technical_trend_delta: null,
  open_flags: [],
  last_call_at: null,
  days_since_last_call: null,
  next_action: null,
};

function rowOf(name: string): HTMLElement {
  return screen.getByText(name).closest("tr")!;
}

/** The consultants of every body row, across the sections, top to bottom. */
function consultantsInOrder(): string[] {
  return screen
    .getAllByRole("row")
    .filter((r) => within(r).queryAllByRole("cell").length > 1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent ?? "");
}

/** Each level section's heading and the consultants in it. */
function sections(): [string, string[]][] {
  return screen.getAllByTestId("level-section").map((section) => [
    within(section).getByRole("heading").textContent ?? "",
    within(section)
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[0].textContent ?? ""),
  ]);
}

function levelCount(name: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(`^${name}\\s*\\d+$`) });
}

describe("RiskBoard", () => {
  beforeAll(() => {
    // Radix Select uses pointer capture and scrolling, which jsdom lacks.
    Element.prototype.hasPointerCapture = vi.fn(() => false);
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    // 20 October 2026, 13:00 in London; only the clock is faked.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-20T12:00:00Z"));
    role = "pmo_manager";
    rows = [
      row({}),
      row({
        placement_id: "p3",
        consultant: { id: "c3", name: "Zoe Green" },
        risk_level: "green",
        overall: 7.6,
        trend: "up",
        trend_delta: 0.6,
        open_flags: [],
        days_since_last_call: 0,
        next_action: {
          id: "a3",
          description: "Book the review",
          owner_role: "sme",
          due_date: "2026-10-25",
        },
      }),
      row(UNSCORED),
    ];
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps the server's order and has no sortable headers", () => {
    render(<RiskBoard />);

    expect(consultantsInOrder()).toEqual([
      "Priya Shah",
      "Zoe Green",
      "Ann Brooks",
    ]);
    expect(screen.queryByRole("button", { name: "Health" })).toBeNull();
  });

  it("groups the placements by level, hiding a level with none", () => {
    rows!.splice(
      1,
      0,
      row({ placement_id: "p4", consultant: { id: "c4", name: "Raj Patel" } }),
    );
    render(<RiskBoard />);

    expect(
      screen.getByText("Every active placement, most at risk first."),
    ).toBeVisible();
    expect(sections()).toEqual([
      ["Red", ["Priya Shah", "Raj Patel"]],
      ["Green", ["Zoe Green"]],
      ["Not scored", ["Ann Brooks"]],
    ]);
    // Each section's header counts its rows.
    expect(
      screen
        .getAllByTestId("level-section")
        .map((s) => s.querySelector("h3")?.nextElementSibling?.textContent),
    ).toEqual(["2", "1", "1"]);
  });

  it("counts every level over the whole board", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    expect(
      screen.getAllByTestId("level-count").map((b) => b.textContent),
    ).toEqual(["Red1", "Amber0", "Green1", "Not scored1"]);

    // Other filters leave the counts as they are.
    await user.click(screen.getByRole("combobox", { name: "Client filter" }));
    await user.click(screen.getByRole("option", { name: "Globex" }));
    expect(levelCount("Red")).toHaveTextContent("Red1");
  });

  it("filters to a level from its count, and back with a second click", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(levelCount("Green"));

    expect(levelCount("Green")).toHaveAttribute("aria-pressed", "true");
    expect(consultantsInOrder()).toEqual(["Zoe Green"]);
    expect(
      screen.getByRole("combobox", { name: "Risk level filter" }),
    ).toHaveTextContent("Green");

    await user.click(levelCount("Green"));

    expect(levelCount("Green")).toHaveAttribute("aria-pressed", "false");
    expect(consultantsInOrder()).toEqual([
      "Priya Shah",
      "Zoe Green",
      "Ann Brooks",
    ]);
    expect(
      screen.getByRole("combobox", { name: "Risk level filter" }),
    ).toHaveTextContent("All levels");
  });

  it("searches the consultant, client, project, flags and next action", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);
    const search = screen.getByLabelText("Search placements");

    await user.click(search);
    await user.paste("globex");
    expect(consultantsInOrder()).toEqual(["Ann Brooks"]);

    await user.clear(search);
    await user.click(search);
    await user.paste("contract horizon");
    expect(consultantsInOrder()).toEqual(["Priya Shah"]);

    await user.clear(search);
    await user.click(search);
    await user.paste("book the");
    expect(consultantsInOrder()).toEqual(["Zoe Green"]);

    await user.clear(search);
    await user.click(search);
    await user.paste("nobody");
    expect(screen.queryAllByTestId("level-section")).toEqual([]);
    expect(
      screen.getByText("No placements match these filters."),
    ).toBeInTheDocument();
  });

  it("shows a placement's health, trend, flags, last call and next action", () => {
    render(<RiskBoard />);

    const tr = rowOf("Priya Shah");
    // The consultant's name opens the placement page.
    expect(
      within(tr).getByRole("link", { name: "Priya Shah" }),
    ).toHaveAttribute("href", "/placements/p1");
    expect(within(tr).getByText("Acme · Data platform")).toBeInTheDocument();
    expect(within(tr).getByText("7")).toBeInTheDocument();
    expect(within(tr).getByTestId("health-badge")).toHaveTextContent("4.6Red");
    expect(
      within(tr).getByLabelText("Falling, -1.2 over 14 days"),
    ).toBeInTheDocument();
    expect(
      within(tr)
        .getAllByTestId("flag")
        .map((f) => f.textContent),
    ).toEqual(["Client dissatisfaction", "Contract horizon"]);
    expect(within(tr).getByText("5 days ago")).toBeInTheDocument();
    // Due 18 October, two days before today: overdue.
    expect(within(tr).getByText("18 Oct 2026 · overdue")).toBeInTheDocument();
    expect(within(tr).getByText("Send the report")).toBeInTheDocument();
  });

  it("shows an action not yet due, a call today and a rising trend", () => {
    render(<RiskBoard />);

    const tr = rowOf("Zoe Green");
    expect(within(tr).getByText("25 Oct 2026")).toBeInTheDocument();
    expect(within(tr).getByText("today")).toBeInTheDocument();
    expect(
      within(tr).getByLabelText("Rising, +0.6 over 14 days"),
    ).toBeInTheDocument();
  });

  it("shows a placement that is not scored yet", () => {
    render(<RiskBoard />);

    const tr = rowOf("Ann Brooks");
    expect(within(tr).getByText("Not scored")).toBeInTheDocument();
    expect(within(tr).getByText("No call yet")).toBeInTheDocument();
    expect(within(tr).queryByTestId("flag")).toBeNull();
  });

  it("filters by risk level, not scored included", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(
      screen.getByRole("combobox", { name: "Risk level filter" }),
    );
    await user.click(screen.getByRole("option", { name: "Not scored" }));

    expect(consultantsInOrder()).toEqual(["Ann Brooks"]);
  });

  it("filters by placement specialist", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(
      screen.getByRole("combobox", { name: "Placement specialist filter" }),
    );
    await user.click(screen.getByRole("option", { name: "Pat Jones" }));

    expect(consultantsInOrder()).toEqual(["Priya Shah", "Zoe Green"]);
  });

  it("filters by the consultant's CDM", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(screen.getByRole("combobox", { name: "CDM filter" }));
    await user.click(screen.getByRole("option", { name: "Lee Tan" }));

    expect(consultantsInOrder()).toEqual(["Priya Shah", "Zoe Green"]);
  });

  it("filters by client", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(screen.getByRole("combobox", { name: "Client filter" }));
    await user.click(screen.getByRole("option", { name: "Globex" }));

    expect(consultantsInOrder()).toEqual(["Ann Brooks"]);
  });

  it("filters by stack", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(screen.getByRole("combobox", { name: "Stack filter" }));
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All stacks",
      "BD",
      "DS",
    ]);
    await user.click(screen.getByRole("option", { name: "DS" }));

    expect(consultantsInOrder()).toEqual(["Priya Shah", "Zoe Green"]);
  });

  it("gives an SME the Technical score only, with no flags or risk filter", () => {
    role = "sme";
    rows = [
      row({
        view: "technical",
        overall: null,
        risk_level: null,
        trend: null,
        trend_delta: null,
        open_flags: [],
      }),
      row({ ...UNSCORED, view: "technical" }),
    ];
    render(<RiskBoard />);

    expect(
      screen.getByRole("columnheader", { name: "Technical" }),
    ).toBeVisible();
    expect(screen.queryByRole("columnheader", { name: "Health" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Flags" })).toBeNull();
    expect(
      screen.queryByRole("combobox", { name: "Risk level filter" }),
    ).toBeNull();
    const tr = rowOf("Priya Shah");
    expect(within(tr).getByText("6.1")).toBeInTheDocument();
    expect(within(tr).queryByTestId("health-badge")).toBeNull();
    expect(
      within(tr).getByLabelText("Steady, +0.2 over 14 days"),
    ).toBeInTheDocument();
    expect(within(rowOf("Ann Brooks")).getByText("Not scored")).toBeVisible();
    // One plain table: no level counts and no level sections.
    expect(screen.queryAllByTestId("level-count")).toEqual([]);
    expect(screen.queryAllByTestId("level-section")).toEqual([]);
    expect(
      screen.getByText(
        "Every placement you support, lowest Technical score first.",
      ),
    ).toBeVisible();
    expect(consultantsInOrder()).toEqual(["Priya Shah", "Ann Brooks"]);
  });

  it("says so when there are no active placements", () => {
    rows = [];
    render(<RiskBoard />);

    expect(screen.getByText(/No active placements yet/)).toBeInTheDocument();
  });
});
