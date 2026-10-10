import { describe, it, expect } from "vitest";
import type { PlacementSession } from "@/types/health";
import {
  PLACEMENT_BUSY_POLL_INTERVAL_MS,
  PLACEMENT_IDLE_POLL_INTERVAL_MS,
  placementHealthPath,
  placementRefreshInterval,
} from "./useHealth";

function call(status: PlacementSession["status"]): PlacementSession {
  return {
    id: `s-${status}`,
    held_at: "2026-10-08T11:00:00Z",
    kind: "technical",
    status,
    duration_seconds: 1_200,
    signal_count: 2,
    action_count: 1,
  };
}

describe("usePlacementHealth", () => {
  it("reads a placement's health by its id", () => {
    expect(placementHealthPath("p1")).toBe("/placements/p1/health");
  });

  it("polls every 10 s while a call of the placement is in flight", () => {
    for (const status of [
      "uploaded",
      "transcribing",
      "transcribed",
      "analyzing",
    ] as const) {
      expect(
        placementRefreshInterval({
          sessions: [call("completed"), call(status)],
        }),
      ).toBe(PLACEMENT_BUSY_POLL_INTERVAL_MS);
    }
  });

  it("polls every 30 s otherwise, before the first read included", () => {
    expect(
      placementRefreshInterval({
        sessions: [call("completed"), call("failed")],
      }),
    ).toBe(PLACEMENT_IDLE_POLL_INTERVAL_MS);
    expect(placementRefreshInterval({ sessions: [] })).toBe(
      PLACEMENT_IDLE_POLL_INTERVAL_MS,
    );
    expect(placementRefreshInterval(undefined)).toBe(
      PLACEMENT_IDLE_POLL_INTERVAL_MS,
    );
  });
});
