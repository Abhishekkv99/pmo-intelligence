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
    tech_lead: { id: "u2", full_name: "Lee Tan", email: "lee@x.com" },
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
  tech_lead: null,
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

function consultantsInOrder(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent ?? "");
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

  it("shows a placement's health, trend, flags, last call and next action", () => {
    render(<RiskBoard />);

    const tr = rowOf("Priya Shah");
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

  it("filters by client", async () => {
    const user = userEvent.setup();
    render(<RiskBoard />);

    await user.click(screen.getByRole("combobox", { name: "Client filter" }));
    await user.click(screen.getByRole("option", { name: "Globex" }));

    expect(consultantsInOrder()).toEqual(["Ann Brooks"]);
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
  });

  it("says so when there are no active placements", () => {
    rows = [];
    render(<RiskBoard />);

    expect(screen.getByText(/No active placements yet/)).toBeInTheDocument();
  });
});
