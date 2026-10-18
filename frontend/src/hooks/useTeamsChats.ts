"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import { IDLE_POLL_INTERVAL_MS, pollInterval } from "@/lib/teams";
import type { QuickAddResult } from "@/types/register";
import type { TeamsChatList } from "@/types/teams";

/**
 * The PMO group chats as Admin > Teams shows them. `enabled` is false unless
 * the Teams tab is open and the user holds a global role: the route answers
 * 403 to anyone else, and a hidden tab should not poll.
 */
export function useTeamsChats(enabled: boolean) {
  // Kept in state and set from each answer, so a running pass is followed
  // closely and an idle list is not.
  const [refreshMs, setRefreshMs] = useState(IDLE_POLL_INTERVAL_MS);
  const { data, error, isLoading, mutate } = useSWR<TeamsChatList>(
    enabled ? API_ROUTES.teamsChats : null,
    {
      refreshInterval: refreshMs,
      onSuccess: (latest) => setRefreshMs(pollInterval(latest)),
    },
  );
  return {
    list: data ?? null,
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

export function requestTeamsScan(): Promise<{ queued: boolean }> {
  return api.post<{ queued: boolean }>(API_ROUTES.teamsScan);
}

export function chooseChatPlacement(
  chatId: string,
  placementId: string,
): Promise<void> {
  return api.put<void>(`${API_ROUTES.teamsChats}/${chatId}/placement`, {
    placement_id: placementId,
  });
}

/** Write the line through the quick add; resolves for line errors too. */
export function createChatPlacement(
  chatId: string,
  line: string,
): Promise<QuickAddResult> {
  return api.post<QuickAddResult>(
    `${API_ROUTES.teamsChats}/${chatId}/placement`,
    { line },
  );
}

export function chooseConsultantMember(
  chatId: string,
  oid: string,
): Promise<void> {
  return api.put<void>(`${API_ROUTES.teamsChats}/${chatId}/consultant-member`, {
    oid,
  });
}
