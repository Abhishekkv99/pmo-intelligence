"use client";

import useSWR from "swr";
import { api, ApiError } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import { anyInFlight } from "@/lib/recordings";
import type {
  PlacementChoice,
  RecordingFolderList,
  SessionCreated,
} from "@/types/recordings";

// While a session is being fetched or transcribed the tab follows it closely;
// otherwise it only picks up the 15-minute scan's new recordings.
export const BUSY_POLL_INTERVAL_MS = 10_000;
export const IDLE_POLL_INTERVAL_MS = 60_000;

/**
 * The recordings folder as the Admin page shows it. `enabled` is false unless
 * the Recordings tab is open and the user holds a global role: the route
 * answers 403 to anyone else, and a hidden tab should not poll.
 */
export function useRecordings(enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<RecordingFolderList>(
    enabled ? API_ROUTES.recordingFolders : null,
    {
      refreshInterval: (latest) =>
        latest && anyInFlight(latest.folders)
          ? BUSY_POLL_INTERVAL_MS
          : IDLE_POLL_INTERVAL_MS,
    },
  );
  return {
    list: data ?? null,
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

export function chooseFolderConsultant(
  folderId: string,
  consultantId: string,
): Promise<void> {
  return api.put<void>(
    `${API_ROUTES.recordingFolders}/${folderId}/consultant`,
    { consultant_id: consultantId },
  );
}

export function requestScan(): Promise<{ queued: boolean }> {
  return api.post<{ queued: boolean }>(API_ROUTES.recordingsScan);
}

export type ProcessOutcome =
  | { kind: "queued"; session: SessionCreated }
  | { kind: "choose"; choice: PlacementChoice };

function isPlacementChoice(body: unknown): body is PlacementChoice {
  return (
    typeof body === "object" &&
    body !== null &&
    Array.isArray((body as { placements?: unknown }).placements)
  );
}

/**
 * Process a recording. A 409 that carries placements means a placement must
 * be chosen; it resolves as `choose` so the dialog can ask. Any other failure
 * rejects with the API's message.
 */
export async function processRecording(
  recordingId: string,
  placementId: string | null,
): Promise<ProcessOutcome> {
  try {
    const session = await api.post<SessionCreated>(
      `${API_ROUTES.recordings}/${recordingId}/process`,
      placementId ? { placement_id: placementId } : {},
    );
    return { kind: "queued", session };
  } catch (err) {
    if (
      err instanceof ApiError &&
      err.status === 409 &&
      isPlacementChoice(err.body)
    ) {
      return { kind: "choose", choice: err.body };
    }
    throw err;
  }
}
