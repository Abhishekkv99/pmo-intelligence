"use client";

import useSWR from "swr";
import { API_ROUTES } from "@/lib/constants";
import type { RiskBoardRow } from "@/types/health";

// The board reads stored snapshots, refreshed after every analysed call and
// register edit, so it follows them every 30 s while it is open (PRD, "How
// health stays current").
export const RISK_BOARD_POLL_INTERVAL_MS = 30_000;

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
