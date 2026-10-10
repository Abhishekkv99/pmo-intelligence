import { describe, it, expect } from "vitest";
import {
  formatDate,
  formatDaysAgo,
  formatDelta,
  formatScore,
  isOverdue,
  RISK_TRIGGER_LABELS,
  RISK_TRIGGERS,
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

  it("calls an action overdue only after its due date", () => {
    expect(isOverdue("2026-10-19", "2026-10-20")).toBe(true);
    expect(isOverdue("2026-10-20", "2026-10-20")).toBe(false);
    expect(isOverdue("2026-10-21", "2026-10-20")).toBe(false);
  });

  it("names every trigger", () => {
    for (const trigger of RISK_TRIGGERS) {
      expect(RISK_TRIGGER_LABELS[trigger]).toBeTruthy();
    }
  });
});
