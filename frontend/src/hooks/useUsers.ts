"use client";

import useSWR from "swr";
import { API_ROUTES } from "@/lib/constants";
import type { UserListItem } from "@/types/register";

/**
 * Every user with their role. For global roles only (the route answers 403
 * otherwise), so `enabled` must be false for anyone else.
 */
export function useUsers(enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<UserListItem[]>(
    enabled ? API_ROUTES.users : null,
  );
  return {
    users: data ?? [],
    isLoading,
    error: error instanceof Error ? error.message : null,
    mutate,
  };
}

/** Users who may be named on a placement: active, with a role. */
export function assignableUsers(users: UserListItem[]): UserListItem[] {
  return users.filter((u) => u.is_active && u.role !== null);
}
