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

/** How each role is named in the UI. */
export const ROLE_LABELS: Record<Role, string> = {
  pmo_manager: "PMO manager",
  sme: "PMO SME",
  tech_lead: "Tech lead",
  ps: "Placement specialist",
  admin: "Admin",
};

export function roleLabel(role: Role | null | undefined): string {
  return role ? ROLE_LABELS[role] : "No role";
}
