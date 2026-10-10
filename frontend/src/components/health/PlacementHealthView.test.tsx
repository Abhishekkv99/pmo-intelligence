import { render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError } from "@/lib/api";
import type {
  EvidenceSignal,
  PlacementHealth,
  SnapshotDetail,
} from "@/types/health";

let state: { health: PlacementHealth | null; error: unknown } = {
  health: null,
  error: null,
};

vi.mock("@/hooks/useHealth", () => ({
  usePlacementHealth: () => ({ ...state, isLoading: false, mutate: vi.fn() }),
}));
// The chart is tested on its own; jsdom cannot lay it out here.
vi.mock("@/components/health/HealthChart", () => ({
  HealthChart: ({ technical }: { technical: boolean }) => (
    <div data-testid="health-chart" data-technical={technical} />
  ),
}));

import { PlacementHealthView } from "./PlacementHealthView";

function signal(overrides: Partial<EvidenceSignal>): EvidenceSignal {
  return {
    id: "g1",
    source_kind: "session",
    source_id: "s1",
    dimension: "delivery",
    polarity: "negative",
    severity: 3,
    confidence: 0.9,
    quote: "The client said they are not happy.",
    note: "The client manager is unhappy with the pace.",
    speaker_role: "consultant",
    occurred_at: "2026-10-17T11:05:00Z",
    offset_ms: 300_000,
    indicator: "client_dissatisfaction",
    ...overrides,
  };
}

const TECHNICAL_SIGNAL = signal({
  id: "g2",
  dimension: "technical",
  severity: 2,
  confidence: 0.8,
  quote: "I am still blocked on the VPN.",
  note: null,
  indicator: null,
  occurred_at: "2026-10-17T11:02:00Z",
});

function latest(overrides: Partial<SnapshotDetail> = {}): SnapshotDetail {
  return {
    computed_at: "2026-10-20T11:30:00Z",
    reason: "call",
    scored: true,
    scores: {
      delivery: 4.4,
      technical: 5.1,
      relationship: 7.8,
      engagement: 7.0,
      onboarding: 7.0,
      communication: 7.0,
    },
    overall: 6.3,
    risk_level: "amber",
    trend: "down",
    trend_delta: -0.9,
    technical_trend: "up",
    technical_trend_delta: 0.6,
    signal_count: 3,
    weights_version: "v1",
    evidence: [
      {
        dimension: "delivery",
        signal_count: 1,
        contributors: [{ signal: signal({}), weight: 0.86, value: 1 }],
      },
      {
        dimension: "technical",
        signal_count: 1,
        contributors: [{ signal: TECHNICAL_SIGNAL, weight: 0.69, value: 3 }],
      },
      { dimension: "relationship", signal_count: 1, contributors: [] },
    ],
    ...overrides,
  };
}

function health(overrides: Partial<PlacementHealth> = {}): PlacementHealth {
  return {
    placement_id: "p1",
    view: "full",
    consultant: { id: "c1", name: "Priya Shah" },
    client: { id: "cl1", name: "Acme" },
    project: { id: "pr1", name: "Data platform" },
    weeks_in: 9,
    register_fields: {
      start_date: "2026-08-18",
      expected_end_date: "2026-11-30",
      status: "active",
      client_manager_name: "Dana Lee",
      ps: { id: "u1", full_name: "Pat Jones", email: "pat@x.com" },
      sme: null,
      tech_lead: { id: "u2", full_name: null, email: "lee@x.com" },
      extension_status: "due",
      rate_band: "B",
      ended_reason: null,
    },
    latest: latest(),
    history: [],
    open_flags: [
      {
        id: "f1",
        trigger: "client_dissatisfaction",
        severity: "critical",
        opened_at: "2026-10-18T11:30:00Z",
        evidence: [signal({})],
      },
      {
        id: "f2",
        trigger: "contract_horizon",
        severity: "high",
        opened_at: "2026-10-18T11:30:00Z",
        evidence: [],
      },
    ],
    sessions: [
      {
        id: "s1",
        held_at: "2026-10-17T11:00:00Z",
        kind: "technical",
        status: "completed",
        duration_seconds: 1_200,
        signal_count: 2,
        action_count: 1,
      },
      {
        id: "s2",
        held_at: "2026-10-03T11:00:00Z",
        kind: null,
        status: "failed",
        duration_seconds: null,
        signal_count: 0,
        action_count: 0,
      },
    ],
    open_issues: [
      {
        id: "i1",
        topic: "VPN access",
        status: "open",
        occurrence_count: 2,
        first_seen_at: "2026-10-03T11:00:00Z",
        last_seen_at: "2026-10-17T11:00:00Z",
      },
    ],
    actions: [
      {
        id: "a1",
        description: "Send the report",
        owner_role: "consultant",
        owner: null,
        quote: "I will send the report.",
        offset_ms: 100,
        due_text: "Friday",
        due_date: "2026-10-18",
        status: "open",
        closed_at: null,
        source_kind: "session",
        source_id: "s1",
      },
      {
        id: "a2",
        description: "Book the review",
        owner_role: "sme",
        owner: { id: "u3", full_name: "Sam Roe", email: "sam@x.com" },
        quote: "I will book the review.",
        offset_ms: 200,
        due_text: null,
        due_date: "2026-10-25",
        status: "open",
        closed_at: null,
        source_kind: "session",
        source_id: "s1",
      },
      {
        id: "a3",
        description: "Ask about access",
        owner_role: "consultant",
        owner: null,
        quote: "I will ask about access.",
        offset_ms: 300,
        due_text: null,
        due_date: null,
        status: "done",
        closed_at: "2026-10-17T11:20:00Z",
        source_kind: "session",
        source_id: "s2",
      },
    ],
    other_placements: [
      {
        id: "p0",
        client: { id: "cl2", name: "Globex" },
        project: { id: "pr2", name: "Billing" },
        start_date: "2025-03-01",
        expected_end_date: "2025-12-31",
        status: "ended",
      },
    ],
    thresholds: { green_from: 7.0, amber_from: 5.0 },
    ...overrides,
  };
}

function tileOf(name: string): HTMLElement {
  return screen
    .getAllByTestId("score-tile")
    .find((t) => within(t).queryByText(name) !== null)!;
}

describe("PlacementHealthView", () => {
  beforeEach(() => {
    // 20 October 2026, 13:00 in London; only the clock is faked.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-20T12:00:00Z"));
    state = { health: health(), error: null };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the header, the overall, the trend and the register fields", () => {
    render(<PlacementHealthView placementId="p1" />);

    expect(
      screen.getByRole("heading", { name: "Priya Shah" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("health-badge")).toHaveTextContent("6.3Amber");
    expect(
      screen.getByLabelText("Falling, -0.9 over 14 days"),
    ).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(
      screen.getByText("Acme · Data platform · 9 weeks in"),
    ).toBeInTheDocument();
    const register = screen.getByTestId("register-fields");
    expect(register).toHaveTextContent("Started18 Aug 2026");
    expect(register).toHaveTextContent("Expected end30 Nov 2026");
    expect(register).toHaveTextContent("Extensiondue");
    expect(register).toHaveTextContent("Rate bandB");
    expect(register).toHaveTextContent("PSPat Jones");
    expect(register).toHaveTextContent("SME—");
    expect(register).toHaveTextContent("Tech leadlee@x.com");
    expect(register).toHaveTextContent("Client managerDana Lee");
    expect(screen.getByTestId("computed-at")).toHaveTextContent(
      "Scored 20 Oct 2026, 12:30 (UK), after a call, from 3 signals",
    );
    expect(screen.getByRole("link", { name: "← Risk board" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("colours each dimension tile by the thresholds and counts its signals", () => {
    render(<PlacementHealthView placementId="p1" />);

    expect(screen.getAllByTestId("score-tile")).toHaveLength(6);
    const delivery = tileOf("Delivery");
    expect(delivery).toHaveTextContent("4.4");
    expect(delivery).toHaveTextContent("Red · 1 signal");
    expect(delivery).toHaveAttribute("aria-label", "Delivery 4.4, red");
    expect(tileOf("Technical")).toHaveTextContent("Amber · 1 signal");
    expect(tileOf("Relationship")).toHaveTextContent("Green · 1 signal");
    expect(tileOf("Engagement")).toHaveTextContent("Green · 0 signals");
    expect(screen.getByTestId("health-chart")).toHaveAttribute(
      "data-technical",
      "false",
    );
  });

  it("lists the open flags with their evidence, and the quotes that moved the scores", () => {
    render(<PlacementHealthView placementId="p1" />);

    const flags = screen.getAllByTestId("flag");
    expect(flags).toHaveLength(2);
    expect(flags[0]).toHaveTextContent("Client dissatisfaction");
    expect(flags[0]).toHaveTextContent("Critical");
    expect(flags[0]).toHaveTextContent("opened 18 Oct 2026");
    const evidence = within(flags[0]).getByTestId("evidence");
    expect(evidence).toHaveTextContent("The client said they are not happy.");
    expect(evidence).toHaveTextContent(
      "severity 3 · confidence 90% · said by Consultant",
    );
    expect(evidence).not.toHaveTextContent("weight");
    expect(
      within(evidence).getByRole("link", {
        name: "said 17 Oct 2026, 12:05 (UK)",
      }),
    ).toHaveAttribute("href", "/sessions/s1");
    expect(flags[1]).toHaveTextContent("Contract horizon");
    expect(flags[1]).toHaveTextContent("Raised from the placement's register");

    const moved = screen.getAllByTestId("contributors");
    // Relationship has a count but no contributor, so it is not listed.
    expect(moved.map((m) => m.textContent?.slice(0, 9))).toEqual([
      "Delivery1",
      "Technical",
    ]);
    const contributor = within(moved[0]).getByTestId("evidence");
    expect(contributor).toHaveTextContent("weight 0.86");
    expect(contributor).toHaveTextContent("Client dissatisfaction");
  });

  it("lists the calls, the open issue, the actions and the other placement", () => {
    render(<PlacementHealthView placementId="p1" />);

    const calls = screen.getAllByTestId("call");
    expect(calls).toHaveLength(2);
    expect(
      within(calls[0]).getByRole("link", { name: "17 Oct 2026, 12:00" }),
    ).toHaveAttribute("href", "/sessions/s1");
    expect(calls[0]).toHaveTextContent("Technical help");
    expect(calls[0]).toHaveTextContent("20 min");
    expect(calls[1]).toHaveTextContent("Not classified");
    expect(calls[1]).toHaveTextContent("Failed");

    const issue = screen.getByTestId("issue");
    expect(issue).toHaveTextContent("VPN access");
    expect(issue).toHaveTextContent("Open");
    expect(issue).toHaveTextContent(
      "seen in 2 calls since 3 Oct 2026, last 17 Oct 2026",
    );

    const actions = screen.getAllByTestId("action");
    expect(actions).toHaveLength(3);
    // Due 18 October, two days before today: overdue.
    expect(actions[0]).toHaveTextContent("Send the report");
    expect(actions[0]).toHaveTextContent("Overdue");
    expect(actions[0]).toHaveTextContent("Owner: Consultant · due 18 Oct 2026");
    expect(actions[1]).toHaveTextContent("Open");
    expect(actions[1]).toHaveTextContent("Owner: Sam Roe · due 25 Oct 2026");
    expect(actions[2]).toHaveAttribute("data-done", "true");
    expect(actions[2]).toHaveTextContent("Done");
    expect(actions[2]).toHaveTextContent("done 17 Oct 2026");
    expect(
      within(actions[0]).getByRole("link", { name: "agreed on a call" }),
    ).toHaveAttribute("href", "/sessions/s1");

    const other = screen.getByTestId("other-placement");
    expect(
      within(other).getByRole("link", { name: "Globex · Billing" }),
    ).toHaveAttribute("href", "/placements/p0");
    expect(other).toHaveTextContent("1 Mar 2025 to 31 Dec 2025 · ended");
  });

  it("gives an SME the Technical score, trend and evidence only", () => {
    state = {
      health: health({
        view: "technical",
        register_fields: {
          ...health().register_fields,
          extension_status: null,
          rate_band: null,
          ended_reason: null,
        },
        latest: latest({
          scores: {
            delivery: null,
            technical: 5.1,
            relationship: null,
            engagement: null,
            onboarding: null,
            communication: null,
          },
          overall: null,
          risk_level: null,
          trend: null,
          trend_delta: null,
          signal_count: null,
          evidence: [
            {
              dimension: "technical",
              signal_count: 1,
              contributors: [
                { signal: TECHNICAL_SIGNAL, weight: 0.69, value: 3 },
              ],
            },
          ],
        }),
        open_flags: [],
        other_placements: [],
      }),
      error: null,
    };
    render(<PlacementHealthView placementId="p1" />);

    expect(screen.getByTestId("technical-score")).toHaveTextContent("5.1");
    expect(screen.queryByTestId("health-badge")).toBeNull();
    expect(screen.getByLabelText("Rising, +0.6 over 14 days")).toBeVisible();
    const tiles = screen.getAllByTestId("score-tile");
    expect(tiles).toHaveLength(1);
    expect(tiles[0]).toHaveTextContent("Technical");
    expect(tiles[0]).toHaveTextContent("1 signal");
    expect(tiles[0]).not.toHaveTextContent("Amber");
    expect(screen.getByTestId("health-chart")).toHaveAttribute(
      "data-technical",
      "true",
    );
    expect(screen.queryByText("Open flags")).toBeNull();
    expect(screen.getAllByTestId("evidence")).toHaveLength(1);
    expect(screen.getByTestId("computed-at")).not.toHaveTextContent("signals");
    const register = screen.getByTestId("register-fields");
    expect(register).not.toHaveTextContent("Extension");
    expect(register).not.toHaveTextContent("Rate band");
    expect(register).toHaveTextContent("PSPat Jones");
  });

  it("shows a placement that is not scored yet, flags included", () => {
    state = {
      health: health({
        latest: latest({
          scored: false,
          scores: {
            delivery: null,
            technical: null,
            relationship: null,
            engagement: null,
            onboarding: null,
            communication: null,
          },
          overall: null,
          risk_level: null,
          trend: null,
          trend_delta: null,
          technical_trend: null,
          technical_trend_delta: null,
          signal_count: 0,
          evidence: [],
        }),
        open_flags: [health().open_flags[1]],
        sessions: [],
        open_issues: [],
        actions: [],
        other_placements: [],
      }),
      error: null,
    };
    render(<PlacementHealthView placementId="p1" />);

    expect(screen.getAllByText("Not scored")).toHaveLength(1);
    expect(screen.getByTestId("computed-at")).toHaveTextContent(
      "no signal in the scoring window",
    );
    for (const tile of screen.getAllByTestId("score-tile")) {
      expect(tile).toHaveTextContent("—");
      expect(tile).toHaveTextContent("0 signals");
    }
    expect(screen.getByTestId("flag")).toHaveTextContent("Contract horizon");
    expect(
      screen.getByText("No signal in the scoring window."),
    ).toBeInTheDocument();
    expect(screen.getByText("No calls yet.")).toBeInTheDocument();
    expect(screen.queryByText("Other placements")).toBeNull();
  });

  it("shows not found before the first recompute's absence is mistaken for data", () => {
    state = { health: health({ latest: null, history: [] }), error: null };
    render(<PlacementHealthView placementId="p1" />);

    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.queryByTestId("computed-at")).toBeNull();
  });

  it("shows not found for a 404, in or out of scope alike", () => {
    state = { health: null, error: new ApiError("Not found", 404) };
    render(<PlacementHealthView placementId="missing" />);

    expect(screen.getByText("Placement not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Risk board" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
