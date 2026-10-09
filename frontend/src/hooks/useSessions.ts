"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import { isInFlight } from "@/lib/recordings";
import type { SessionKind } from "@/lib/sessions";
import type { SessionCreated } from "@/types/recordings";
import type {
  MediaUrl,
  SessionDetail,
  SessionListItem,
} from "@/types/sessions";

// While a session's job may still change it the list and the page follow it
// closely; otherwise the list only picks up new sessions now and then.
export const BUSY_POLL_INTERVAL_MS = 10_000;
export const IDLE_POLL_INTERVAL_MS = 60_000;

export function sessionPath(sessionId: string): string {
  return `${API_ROUTES.sessions}/${sessionId}`;
}

/** The sessions in the caller's scope, newest call first. */
export function useSessions() {
  const { data, error, isLoading, mutate } = useSWR<SessionListItem[]>(
    API_ROUTES.sessions,
    {
      refreshInterval: (latest) =>
        latest?.some((s) => isInFlight(s.status))
          ? BUSY_POLL_INTERVAL_MS
          : IDLE_POLL_INTERVAL_MS,
    },
  );
  return {
    sessions: data ?? null,
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

/** Every 10 s while the session's job may still change it; else never. */
export function sessionRefreshInterval(latest?: SessionDetail): number {
  return latest && isInFlight(latest.status) ? BUSY_POLL_INTERVAL_MS : 0;
}

/**
 * One session's page. Polls every 10 s while its job may still change it,
 * and not at all once it is completed or failed. A session outside the
 * caller's scope answers 404, exactly as a missing one.
 */
export function useSession(sessionId: string) {
  // Held in state, not passed as a function: SWR schedules its timer only
  // when the option changes, so a function answering 0 for a session first
  // seen completed or failed would never start polling after a retry.
  const [refreshInterval, setRefreshInterval] = useState(0);
  const { data, error, isLoading, mutate } = useSWR<SessionDetail>(
    sessionPath(sessionId),
    {
      refreshInterval,
      onSuccess: (latest) => setRefreshInterval(sessionRefreshInterval(latest)),
    },
  );
  return {
    session: data ?? null,
    isLoading,
    error: (error as unknown) ?? null,
    mutate,
  };
}

/**
 * A 15-minute URL to play the recording from. Fetched once per page; the
 * player asks for a fresh one (`refresh`) when the old one stops working.
 */
export function useMediaUrl(sessionId: string) {
  const { data, error, mutate } = useSWR<MediaUrl>(
    `${sessionPath(sessionId)}/media-url`,
    { revalidateOnFocus: false, revalidateIfStale: false },
  );
  return {
    media: data ?? null,
    error: error instanceof Error ? error.message : null,
    refresh: () => mutate(),
  };
}

export function setSessionKind(
  sessionId: string,
  kind: SessionKind,
): Promise<SessionDetail> {
  return api.patch<SessionDetail>(`${sessionPath(sessionId)}/kind`, { kind });
}

export function retrySession(sessionId: string): Promise<SessionCreated> {
  return api.post<SessionCreated>(`${sessionPath(sessionId)}/retry`);
}
