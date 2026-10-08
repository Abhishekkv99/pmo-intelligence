"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import type { Role } from "@/lib/roles";
import type { UserListItem } from "@/types/register";

export interface RoleChangeResult {
  user: UserListItem;
  /** What changed, in words: sessions ended, a bootstrap-admin warning. */
  message: string;
}

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

/** Give an address a role; creates the user if they have never signed in. */
export function grantRole(
  email: string,
  role: Role,
): Promise<RoleChangeResult> {
  return api.post<RoleChangeResult>(API_ROUTES.users, { email, role });
}

/** Change a user's role, or remove it with null (which ends their sessions). */
export function changeRole(
  userId: string,
  role: Role | null,
): Promise<RoleChangeResult> {
  return api.patch<RoleChangeResult>(`${API_ROUTES.users}/${userId}`, { role });
}
