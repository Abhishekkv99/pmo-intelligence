/**
 * Register enumerations. Mirrors `ConsultantStatus`, `ExtensionStatus` and
 * `PlacementStatus` in `backend/app/models/enums.py`, the single source for
 * these values; keep the two in step.
 */
export const CONSULTANT_STATUSES = ["bench", "placed", "left"] as const;
export type ConsultantStatus = (typeof CONSULTANT_STATUSES)[number];

export const EXTENSION_STATUSES = [
  "not_due",
  "due",
  "requested",
  "confirmed",
  "declined",
] as const;
export type ExtensionStatus = (typeof EXTENSION_STATUSES)[number];

export const PLACEMENT_STATUSES = ["active", "ended", "terminated"] as const;
export type PlacementStatus = (typeof PLACEMENT_STATUSES)[number];

/** "not_due" -> "Not due": enumeration values as shown in the UI. */
export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
