import { render, screen } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { describe, it, expect, vi } from "vitest";
import type { PlacementSession, SnapshotPoint } from "@/types/health";

vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    // jsdom lays nothing out, so the responsive container never measures a
    // size and draws nothing; give the chart one so its marks render.
    ResponsiveContainer: ({
      children,
    }: {
      children: ReactElement<{ width?: number; height?: number }>;
    }) => cloneElement(children, { width: 640, height: 240 }),
  };
});

import { HealthChart } from "./HealthChart";

const THRESHOLDS = { green_from: 7, amber_from: 5 };

function snapshot(overrides: Partial<SnapshotPoint>): SnapshotPoint {
  return {
    computed_at: "2026-10-01T06:00:00Z",
    reason: "daily",
    scored: true,
    scores: {
      delivery: 6.0,
      technical: 5.1,
      relationship: 7.4,
      engagement: 6.8,
      onboarding: 7.0,
      communication: 7.0,
    },
    overall: 6.4,
    risk_level: "amber",
    trend: "flat",
    technical_trend: "up",
    ...overrides,
  };
}

function call(overrides: Partial<PlacementSession>): PlacementSession {
  return {
    id: "s1",
    held_at: "2026-10-03T11:00:00Z",
    kind: "technical",
    status: "completed",
    duration_seconds: 1_200,
    signal_count: 2,
    action_count: 1,
    ...overrides,
  };
}

const HISTORY = [
  snapshot({}),
  snapshot({
    computed_at: "2026-10-05T06:00:00Z",
    scored: false,
    overall: null,
    risk_level: null,
  }),
  snapshot({
    computed_at: "2026-10-09T06:00:00Z",
    overall: 5.8,
    reason: "call",
  }),
];

describe("HealthChart", () => {
  it("draws a dot per scored snapshot, a line per completed call and the bands", () => {
    const { container } = render(
      <HealthChart
        history={HISTORY}
        sessions={[
          call({}),
          call({ id: "s2", held_at: "2026-10-08T11:00:00Z" }),
          call({ id: "s3", status: "failed" }),
        ]}
        thresholds={THRESHOLDS}
        technical={false}
      />,
    );

    expect(screen.getByTestId("health-chart")).toBeInTheDocument();
    // Two scored snapshots; the unscored one between them leaves a gap.
    expect(container.querySelectorAll(".recharts-line-dot")).toHaveLength(2);
    // Two completed calls; the failed one is not marked.
    expect(container.querySelectorAll(".recharts-reference-line")).toHaveLength(
      2,
    );
    // Green, amber and red bands.
    expect(container.querySelectorAll(".recharts-reference-area")).toHaveLength(
      3,
    );
    // 30 September to 10 October: a tick every second UK midnight, all drawn.
    expect(
      container.querySelectorAll(
        ".recharts-xAxis .recharts-cartesian-axis-tick",
      ),
    ).toHaveLength(5);
    expect(
      screen.getByText(/Green from 7\.0, amber from 5\.0, red below/),
    ).toBeInTheDocument();
  });

  it("plots the Technical score without bands in the technical view", () => {
    const { container } = render(
      <HealthChart
        history={[snapshot({ overall: null, risk_level: null })]}
        sessions={[call({})]}
        thresholds={THRESHOLDS}
        technical
      />,
    );

    expect(container.querySelectorAll(".recharts-line-dot")).toHaveLength(1);
    expect(container.querySelectorAll(".recharts-reference-area")).toHaveLength(
      0,
    );
    expect(
      screen.getByText(/Technical score after every recompute/),
    ).toBeVisible();
    expect(screen.queryByText(/Green from/)).toBeNull();
  });

  it("says so before any snapshot is scored", () => {
    render(
      <HealthChart
        history={[
          snapshot({
            scored: false,
            overall: null,
            risk_level: null,
            trend: null,
          }),
        ]}
        sessions={[]}
        thresholds={THRESHOLDS}
        technical={false}
      />,
    );

    expect(screen.getByTestId("chart-empty")).toHaveTextContent("No score yet");
    expect(screen.queryByTestId("health-chart")).toBeNull();
  });
});
