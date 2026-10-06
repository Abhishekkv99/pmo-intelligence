"use client";

import useSWR from "swr";
import { API_ROUTES } from "@/lib/constants";
import type { ProcessingStatusResponse } from "@/types/processing";

// While something is queued or running the panel follows it closely; an idle
// queue still refreshes so the memory reading does not go stale, just less often.
const BUSY_POLL_INTERVAL_MS = 5000;
const IDLE_POLL_INTERVAL_MS = 30000;

export function isQueueBusy(
  data: ProcessingStatusResponse | undefined,
): boolean {
  if (!data) return false;
  return data.queue_depth > 0 || data.running.length > 0;
}

/**
 * Point-in-time view of the processing queue and the backend's memory.
 *
 * `enabled` must be false for anyone without a global role (`pmo_manager` or
 * `admin`): the route answers 403 otherwise, so the panel is never requested
 * for them rather than rendering an error they cannot act on.
 */
export function useProcessingStatus(enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<ProcessingStatusResponse>(
    enabled ? API_ROUTES.processingStatus : null,
    {
      refreshInterval: (latestData) =>
        isQueueBusy(latestData) ? BUSY_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS,
    },
  );

  return {
    status: data ?? null,
    isBusy: isQueueBusy(data),
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}
