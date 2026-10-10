/**
 * Placement health in the UI. The enumerations mirror `RiskLevel`, `Trend`,
 * `RiskTrigger`, `FlagSeverity`, `HealthView` and `SnapshotReason` in
 * `backend/app/models/enums.py`, the single source for these values; keep
 * the two in step.
 */

export const RISK_LEVELS = ["red", "amber", "green"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export const TRENDS = ["up", "flat", "down"] as const;
export type Trend = (typeof TRENDS)[number];

export const RISK_TRIGGERS = [
  "gone_quiet",
  "client_dissatisfaction",
  "repeated_blocker",
  "downward_trend",
  "relationship_strain",
  "contract_horizon",
  "intent_to_leave",
  "missed_commitment",
] as const;
export type RiskTrigger = (typeof RISK_TRIGGERS)[number];

export const FLAG_SEVERITIES = ["medium", "high", "critical"] as const;
export type FlagSeverity = (typeof FLAG_SEVERITIES)[number];

/** `full`: every dimension; `technical`: an SME, the Technical score only. */
export const HEALTH_VIEWS = ["full", "technical"] as const;
export type HealthView = (typeof HEALTH_VIEWS)[number];

export const SNAPSHOT_REASONS = [
  "call",
  "register",
  "daily",
  "catch_up",
] as const;
export type SnapshotReason = (typeof SNAPSHOT_REASONS)[number];

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  red: "Red",
  amber: "Amber",
  green: "Green",
};

/** The PRD's names for the early-warning triggers. */
export const RISK_TRIGGER_LABELS: Record<RiskTrigger, string> = {
  gone_quiet: "Gone quiet",
  client_dissatisfaction: "Client dissatisfaction",
  repeated_blocker: "Repeated blocker",
  downward_trend: "Downward trend",
  relationship_strain: "Relationship strain",
  contract_horizon: "Contract horizon",
  intent_to_leave: "Intent to leave",
  missed_commitment: "Missed commitment",
};

export const FLAG_SEVERITY_LABELS: Record<FlagSeverity, string> = {
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const TREND_LABELS: Record<Trend, string> = {
  up: "Rising",
  flat: "Steady",
  down: "Falling",
};

const UK_TIME_ZONE = "Europe/London";

/** A score as stored: one decimal, "7.0". */
export function formatScore(score: number): string {
  return score.toFixed(1);
}

/** A trend's change with its sign: "+0.6", "-1.2", "0.0". */
export function formatDelta(delta: number): string {
  return delta > 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);
}

/** Days since the last call, in words: "today", "1 day ago", "5 days ago". */
export function formatDaysAgo(days: number): string {
  if (days <= 0) return "today";
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** Today's date on a UK calendar, as "YYYY-MM-DD". */
export function ukToday(now: Date = new Date()): string {
  // en-CA writes dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: UK_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** A calendar date ("2026-10-18") as shown on the page: "18 Oct 2026". */
export function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

/** True when a due date ("YYYY-MM-DD") is before the UK date today. */
export function isOverdue(dueDate: string, today: string = ukToday()): boolean {
  return dueDate < today;
}
