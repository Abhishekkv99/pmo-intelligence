import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ProcessingStatusResponse } from "@/types/processing";

let mockSwrReturn: Record<string, unknown> = {};
let capturedKey: string | null | undefined;
let capturedSwrOptions: Record<string, unknown> | undefined;

vi.mock("swr", () => ({
  default: (key: string | null, options?: Record<string, unknown>) => {
    capturedKey = key;
    capturedSwrOptions = options;
    return mockSwrReturn;
  },
}));

import { isQueueBusy, useProcessingStatus } from "./useProcessingStatus";

function makeStatus(
  overrides: Partial<ProcessingStatusResponse> = {},
): ProcessingStatusResponse {
  return {
    queue_depth: 0,
    capacity: 1,
    running: [],
    rss_mib: 400,
    memory_diagnostics_enabled: false,
    ...overrides,
  };
}

describe("useProcessingStatus", () => {
  beforeEach(() => {
    mockSwrReturn = {
      data: undefined,
      error: undefined,
      isLoading: true,
      mutate: vi.fn(),
    };
    capturedKey = undefined;
    capturedSwrOptions = undefined;
  });

  it("never requests the route when disabled", () => {
    const { result } = renderHook(() => useProcessingStatus(false));
    expect(capturedKey).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.isBusy).toBe(false);
  });

  it("polls every 5s while busy and every 30s when idle", () => {
    renderHook(() => useProcessingStatus(true));
    expect(capturedKey).toBe("/processing/status");

    const refreshInterval = capturedSwrOptions!.refreshInterval as (
      data: ProcessingStatusResponse | undefined,
    ) => number;
    expect(refreshInterval(makeStatus({ queue_depth: 3 }))).toBe(5000);
    expect(
      refreshInterval(
        makeStatus({
          running: [
            {
              kind: "analyze",
              id: "int-1",
              started_at: "2026-09-21T20:15:00Z",
              worker: 0,
            },
          ],
        }),
      ),
    ).toBe(5000);
    expect(refreshInterval(makeStatus())).toBe(30000);
    // Before the first response there is nothing to be busy about.
    expect(refreshInterval(undefined)).toBe(30000);
  });

  it("derives isBusy from depth or running jobs", () => {
    expect(isQueueBusy(undefined)).toBe(false);
    expect(isQueueBusy(makeStatus())).toBe(false);
    expect(isQueueBusy(makeStatus({ queue_depth: 1 }))).toBe(true);

    mockSwrReturn = {
      data: makeStatus({ queue_depth: 2 }),
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    };
    const { result } = renderHook(() => useProcessingStatus(true));
    expect(result.current.isBusy).toBe(true);
    expect(result.current.status?.queue_depth).toBe(2);
  });
});
