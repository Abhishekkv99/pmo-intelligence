/**
 * User roles. Mirrors `Role` and `GLOBAL_ROLES` in `backend/app/models/enums.py`,
 * the single source for these values; keep the two in step.
 */
export const ROLES = [
  "pmo_manager",
  "sme",
  "tech_lead",
  "ps",
  "admin",
] as const;

export type Role = (typeof ROLES)[number];

/** Roles that read every placement; the others read only the placements naming them. */
export const GLOBAL_ROLES: readonly Role[] = ["pmo_manager", "admin"];

/** True for a global role. `null` (a new account with no role yet) reads nothing. */
export function hasGlobalRole(role: Role | null | undefined): boolean {
  return role != null && GLOBAL_ROLES.includes(role);
}
