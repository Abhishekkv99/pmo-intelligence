import { describe, it, expect } from "vitest";
import { DIMENSIONS } from "@/lib/sessions";
import type { PlacementSession, SnapshotPoint } from "@/types/health";
import {
  callMarkers,
  chartDomain,
  chartPoints,
  chartTicks,
  DIMENSION_LABELS,
  formatDate,
  formatDaysAgo,
  formatDelta,
  formatScore,
  formatUkAxisDate,
  formatUkDate,
  formatWeeksIn,
  isOverdue,
  placementPath,
  riskLevelFor,
  RISK_TRIGGER_LABELS,
  RISK_TRIGGERS,
  SIGNAL_INDICATOR_LABELS,
  SIGNAL_INDICATORS,
  SNAPSHOT_REASON_LABELS,
  SNAPSHOT_REASONS,
  ukToday,
} from "./health";

describe("health formatting", () => {
  it("shows scores with one decimal and deltas with their sign", () => {
    expect(formatScore(7)).toBe("7.0");
    expect(formatScore(4.55)).toBe("4.5");
    expect(formatDelta(0.6)).toBe("+0.6");
    expect(formatDelta(-1.2)).toBe("-1.2");
    expect(formatDelta(0)).toBe("0.0");
  });

  it("says how long ago the last call was", () => {
    expect(formatDaysAgo(0)).toBe("today");
    expect(formatDaysAgo(1)).toBe("1 day ago");
    expect(formatDaysAgo(12)).toBe("12 days ago");
  });

  it("says how many weeks in a placement is", () => {
    expect(formatWeeksIn(0)).toBe("0 weeks in");
    expect(formatWeeksIn(1)).toBe("1 week in");
    expect(formatWeeksIn(9)).toBe("9 weeks in");
  });

  it("shows a calendar date without moving it by the time zone", () => {
    expect(formatDate("2026-10-18")).toBe("18 Oct 2026");
    expect(formatDate("2027-01-01")).toBe("1 Jan 2027");
  });

  it("takes today's date from the UK calendar", () => {
    // 23:30 UTC on 24 September is 00:30 on the 25th in London (BST).
    expect(ukToday(new Date("2026-09-24T23:30:00Z"))).toBe("2026-09-25");
    // In winter London is on UTC.
    expect(ukToday(new Date("2026-12-24T23:30:00Z"))).toBe("2026-12-24");
  });

  it("shows an instant as the UK date it fell on, long and short", () => {
    expect(formatUkDate("2026-09-24T23:30:00Z")).toBe("25 Sept 2026");
    expect(formatUkDate("2026-12-24T23:30:00Z")).toBe("24 Dec 2026");
    expect(formatUkAxisDate(Date.parse("2026-09-24T23:30:00Z"))).toBe(
      "25 Sept",
    );
  });

  it("calls an action overdue only after its due date", () => {
    expect(isOverdue("2026-10-19", "2026-10-20")).toBe(true);
    expect(isOverdue("2026-10-20", "2026-10-20")).toBe(false);
    expect(isOverdue("2026-10-21", "2026-10-20")).toBe(false);
  });

  it("builds the placement page's path", () => {
    expect(placementPath("p1")).toBe("/placements/p1");
  });

  it("names every trigger, indicator, snapshot reason and dimension", () => {
    for (const trigger of RISK_TRIGGERS) {
      expect(RISK_TRIGGER_LABELS[trigger]).toBeTruthy();
    }
    for (const indicator of SIGNAL_INDICATORS) {
      expect(SIGNAL_INDICATOR_LABELS[indicator]).toBeTruthy();
    }
    for (const reason of SNAPSHOT_REASONS) {
      expect(SNAPSHOT_REASON_LABELS[reason]).toBeTruthy();
    }
    for (const dimension of DIMENSIONS) {
      expect(DIMENSION_LABELS[dimension]).toBeTruthy();
    }
  });
});

describe("score levels", () => {
  const thresholds = { green_from: 7.0, amber_from: 5.0 };

  it("places a score in its level by the thresholds the API returned", () => {
    expect(riskLevelFor(10, thresholds)).toBe("green");
    expect(riskLevelFor(7.0, thresholds)).toBe("green");
    expect(riskLevelFor(6.9, thresholds)).toBe("amber");
    expect(riskLevelFor(5.0, thresholds)).toBe("amber");
    expect(riskLevelFor(4.9, thresholds)).toBe("red");
    expect(riskLevelFor(1, thresholds)).toBe("red");
  });

  it("follows other thresholds just the same", () => {
    const stricter = { green_from: 8.0, amber_from: 6.0 };
    expect(riskLevelFor(7.0, stricter)).toBe("amber");
    expect(riskLevelFor(5.9, stricter)).toBe("red");
  });
});

describe("chart data", () => {
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

  const DAY = 86_400_000;

  it("plots the overall with its level, leaving a gap where nothing was scored", () => {
    const points = chartPoints(
      [
        snapshot({}),
        snapshot({
          computed_at: "2026-10-05T06:00:00Z",
          scored: false,
          overall: null,
          risk_level: null,
          reason: "call",
        }),
      ],
      false,
    );

    expect(points).toEqual([
      {
        t: Date.parse("2026-10-01T06:00:00Z"),
        computed_at: "2026-10-01T06:00:00Z",
        score: 6.4,
        level: "amber",
        reason: "daily",
      },
      {
        t: Date.parse("2026-10-05T06:00:00Z"),
        computed_at: "2026-10-05T06:00:00Z",
        score: null,
        level: null,
        reason: "call",
      },
    ]);
  });

  it("plots the Technical score without a level in the technical view", () => {
    const [point] = chartPoints(
      [snapshot({ overall: null, risk_level: null })],
      true,
    );

    expect(point.score).toBe(5.1);
    expect(point.level).toBeNull();
  });

  it("marks the completed calls only, oldest first", () => {
    expect(
      callMarkers([
        call({ id: "s3", held_at: "2026-10-10T11:00:00Z" }),
        call({ id: "s2", held_at: "2026-10-07T11:00:00Z", status: "failed" }),
        call({}),
      ]),
    ).toEqual([
      Date.parse("2026-10-03T11:00:00Z"),
      Date.parse("2026-10-10T11:00:00Z"),
    ]);
  });

  it("spans every point and marker with a day's air each side", () => {
    const first = Date.parse("2026-10-01T06:00:00Z");
    const last = Date.parse("2026-10-10T11:00:00Z");

    expect(chartDomain([last, first, first + DAY])).toEqual([
      first - DAY,
      last + DAY,
    ]);
    expect(chartDomain([])).toEqual([0, DAY]);
  });

  const instants = (isos: string[]) => isos.map((iso) => Date.parse(iso));

  it("ticks the axis at UK midnights, daily over a few days", () => {
    // The span starts at 12:00 BST on 6 October, so the first tick is the
    // 7th's midnight (23:00 UTC on the 6th), the last the 11th's.
    expect(
      chartTicks([
        Date.parse("2026-10-06T11:00:00Z"),
        Date.parse("2026-10-11T20:08:00Z"),
      ]),
    ).toEqual(
      instants([
        "2026-10-06T23:00:00Z",
        "2026-10-07T23:00:00Z",
        "2026-10-08T23:00:00Z",
        "2026-10-09T23:00:00Z",
        "2026-10-10T23:00:00Z",
      ]),
    );
  });

  it("widens the step so a long span has at most six ticks", () => {
    // 60 days: daily, every 2 and every 7 days would need more than six.
    expect(
      chartTicks([
        Date.parse("2026-08-10T00:00:00Z"),
        Date.parse("2026-10-09T00:00:00Z"),
      ]),
    ).toEqual(
      instants([
        "2026-08-10T23:00:00Z",
        "2026-08-24T23:00:00Z",
        "2026-09-07T23:00:00Z",
        "2026-09-21T23:00:00Z",
        "2026-10-05T23:00:00Z",
      ]),
    );
  });

  it("keeps the ticks on UK midnight across the clock change", () => {
    // BST ends on 25 October 2026: midnight moves from 23:00 to 00:00 UTC.
    expect(
      chartTicks([
        Date.parse("2026-10-23T12:00:00Z"),
        Date.parse("2026-10-27T12:00:00Z"),
      ]),
    ).toEqual(
      instants([
        "2026-10-23T23:00:00Z",
        "2026-10-24T23:00:00Z",
        "2026-10-26T00:00:00Z",
        "2026-10-27T00:00:00Z",
      ]),
    );
  });
});
