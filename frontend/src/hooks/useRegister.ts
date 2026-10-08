"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import type {
  Client,
  Consultant,
  ImportResult,
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

/** Preview (`dryRun`) or apply a register CSV. Always resolves for row errors. */
export function importRegister(
  file: File,
  dryRun: boolean,
): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return api.postFormData<ImportResult>(API_ROUTES.registerImport, form, {
    params: { dry_run: String(dryRun) },
  });
}
