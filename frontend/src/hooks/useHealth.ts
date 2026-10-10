"use client";

import useSWR from "swr";
import { API_ROUTES } from "@/lib/constants";
import { isInFlight } from "@/lib/recordings";
import type { PlacementHealth, RiskBoardRow } from "@/types/health";

// The board reads stored snapshots, refreshed after every analysed call and
// register edit, so it follows them every 30 s while it is open (PRD, "How
// health stays current").
export const RISK_BOARD_POLL_INTERVAL_MS = 30_000;

// The placement page follows a call of its placement that is still being
// processed every 10 s, as the PRD asks, and the daily and register
// recomputes every 30 s otherwise.
export const PLACEMENT_BUSY_POLL_INTERVAL_MS = 10_000;
export const PLACEMENT_IDLE_POLL_INTERVAL_MS = 30_000;

/** The active placements in the caller's scope, in the server's board order. */
export function useRiskBoard() {
  const { data, error, isLoading, mutate } = useSWR<RiskBoardRow[]>(
    API_ROUTES.riskBoard,
    { refreshInterval: RISK_BOARD_POLL_INTERVAL_MS },
  );
  return {
    rows: data ?? null,
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

export function placementHealthPath(placementId: string): string {
  return `${API_ROUTES.placements}/${placementId}/health`;
}

/** Every 10 s while a call of the placement is in flight, else every 30 s. */
export function placementRefreshInterval(
  latest?: Pick<PlacementHealth, "sessions">,
): number {
  return latest?.sessions.some((s) => isInFlight(s.status))
    ? PLACEMENT_BUSY_POLL_INTERVAL_MS
    : PLACEMENT_IDLE_POLL_INTERVAL_MS;
}

/**
 * One placement's health page. A placement outside the caller's scope
 * answers 404, exactly as a missing one. The interval never answers 0, so a
 * function of the data is safe here (see `useSession` for the other case).
 */
export function usePlacementHealth(placementId: string) {
  const { data, error, isLoading, mutate } = useSWR<PlacementHealth>(
    placementHealthPath(placementId),
    { refreshInterval: (latest) => placementRefreshInterval(latest) },
  );
  return {
    health: data ?? null,
    isLoading,
    error: (error as unknown) ?? null,
    mutate,
  };
}
