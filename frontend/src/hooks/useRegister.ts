"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import type {
  Client,
  Consultant,
  QuickAddResult,
  Placement,
  Project,
} from "@/types/register";

/**
 * The placement register, for the admin pages. Every list route answers 403
 * to anyone without a global role, so `enabled` must be false for them and
 * nothing is requested.
 */
function useList<T>(path: string, enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<T[]>(enabled ? path : null);
  return {
    items: data ?? [],
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

export function usePlacements(enabled: boolean) {
  return useList<Placement>(API_ROUTES.placements, enabled);
}

export function useConsultants(enabled: boolean) {
  return useList<Consultant>(API_ROUTES.consultants, enabled);
}

export function useClients(enabled: boolean) {
  return useList<Client>(API_ROUTES.clients, enabled);
}

export function useProjects(enabled: boolean) {
  return useList<Project>(API_ROUTES.projects, enabled);
}

/** Create when `id` is null, otherwise update the fields in `body`. */
export function saveRecord<T>(
  path: string,
  id: string | null,
  body: Record<string, unknown>,
): Promise<T> {
  return id === null
    ? api.post<T>(path, body)
    : api.patch<T>(`${path}/${id}`, body);
}

/**
 * Preview (`dryRun`) or apply quick-add lines in the Teams chat name format.
 * Always resolves for line errors; the lines say why.
 */
export function quickAdd(
  lines: string[],
  dryRun: boolean,
): Promise<QuickAddResult> {
  return api.post<QuickAddResult>(
    API_ROUTES.registerQuickAdd,
    { lines },
    { params: { dry_run: String(dryRun) } },
  );
}
