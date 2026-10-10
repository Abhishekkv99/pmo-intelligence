/**
 * Placement health in the UI. The enumerations mirror `RiskLevel`, `Trend`,
 * `RiskTrigger`, `FlagSeverity`, `HealthView`, `SnapshotReason`, `SourceKind`
 * and `SignalIndicator` in `backend/app/models/enums.py`, the single source
 * for these values; keep the two in step. The RAG thresholds are never
 * mirrored: the placement health API returns the configuration's.
 */

import { ROUTES } from "@/lib/constants";
import { ukLocalToIso } from "@/lib/recordings";
import type { Dimension } from "@/lib/sessions";
import type {
  PlacementSession,
  RagThresholds,
  SnapshotPoint,
} from "@/types/health";

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

export const SOURCE_KINDS = ["session", "message"] as const;
export type SourceKind = (typeof SOURCE_KINDS)[number];

export const SIGNAL_INDICATORS = [
  "client_dissatisfaction",
  "consultant_change_requested",
  "intent_to_leave",
] as const;
export type SignalIndicator = (typeof SIGNAL_INDICATORS)[number];

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

/** Why a snapshot was computed, as the page says it. */
export const SNAPSHOT_REASON_LABELS: Record<SnapshotReason, string> = {
  call: "After a call",
  register: "After a register edit",
  daily: "Daily recompute",
  catch_up: "Catch-up after a deploy",
};

/** What a critical indicator tags a quote as saying. */
export const SIGNAL_INDICATOR_LABELS: Record<SignalIndicator, string> = {
  client_dissatisfaction: "Client dissatisfaction",
  consultant_change_requested: "Change of consultant requested",
  intent_to_leave: "Intent to leave",
};

export const DIMENSION_LABELS: Record<Dimension, string> = {
  delivery: "Delivery",
  technical: "Technical",
  relationship: "Relationship",
  engagement: "Engagement",
  onboarding: "Onboarding",
  communication: "Communication",
};

const UK_TIME_ZONE = "Europe/London";

/** The placement (consultant) page's path. */
export function placementPath(placementId: string): string {
  return `${ROUTES.placements}/${placementId}`;
}

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

/** Whole weeks since the start, in words: "9 weeks in", "1 week in". */
export function formatWeeksIn(weeks: number): string {
  return weeks === 1 ? "1 week in" : `${weeks} weeks in`;
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

/** An instant as the UK calendar date it fell on: "18 Oct 2026". */
export function formatUkDate(iso: string): string {
  return formatDate(ukToday(new Date(iso)));
}

/** An instant as a short UK date for the chart's axis: "18 Oct". */
export function formatUkAxisDate(ms: number): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: UK_TIME_ZONE,
    day: "numeric",
    month: "short",
  }).format(new Date(ms));
}

/** True when a due date ("YYYY-MM-DD") is before the UK date today. */
export function isOverdue(dueDate: string, today: string = ukToday()): boolean {
  return dueDate < today;
}

/**
 * The RAG level a score falls in, by the thresholds the API returns (green
 * from `green_from`, amber from `amber_from`, red below). The server decides
 * the overall's level, which an open critical flag can lower; this is for
 * the dimension tiles, which have no flags.
 */
export function riskLevelFor(
  score: number,
  thresholds: RagThresholds,
): RiskLevel {
  if (score >= thresholds.green_from) return "green";
  if (score >= thresholds.amber_from) return "amber";
  return "red";
}

/** One snapshot on the health chart's time axis. */
export interface ChartPoint {
  /** `computed_at` in epoch milliseconds, the x value. */
  t: number;
  computed_at: string;
  /** The overall (the Technical score in the technical view); null when not scored. */
  score: number | null;
  /** The overall's level; null in the technical view and when not scored. */
  level: RiskLevel | null;
  reason: SnapshotReason;
}

/** Every snapshot as a chart point, in the order given (oldest first). */
export function chartPoints(
  history: SnapshotPoint[],
  technical: boolean,
): ChartPoint[] {
  return history.map((s) => ({
    t: Date.parse(s.computed_at),
    computed_at: s.computed_at,
    score: technical ? s.scores.technical : s.overall,
    level: technical ? null : s.risk_level,
    reason: s.reason,
  }));
}

/** The completed calls' times, oldest first: the chart's markers. */
export function callMarkers(sessions: PlacementSession[]): number[] {
  return sessions
    .filter((s) => s.status === "completed")
    .map((s) => Date.parse(s.held_at))
    .sort((a, b) => a - b);
}

const DAY_MS = 86_400_000;

/** The chart's time span: every point and marker, with a day's air each side. */
export function chartDomain(times: number[]): [number, number] {
  if (times.length === 0) return [0, DAY_MS];
  return [Math.min(...times) - DAY_MS, Math.max(...times) + DAY_MS];
}

const TICK_STEPS_DAYS = [1, 2, 7, 14, 28, 91, 182, 365];
const MAX_TICKS = 6;

/** The UK midnight that starts a UK date ("YYYY-MM-DD"), in epoch milliseconds. */
function ukMidnight(date: string): number {
  return Date.parse(ukLocalToIso(`${date}T00:00`));
}

function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/**
 * The chart's x-axis ticks: UK midnights across the span, every 1, 2, 7, 14,
 * 28, 91, 182 or 365 days, the smallest step that needs at most six. The
 * chart gives Recharts these outright: its own time ticks fall on the
 * browser's local midnight, and on this axis it draws only one of them.
 */
export function chartTicks([start, end]: [number, number]): number[] {
  const spanDays = (end - start) / DAY_MS;
  const step =
    TICK_STEPS_DAYS.find((s) => spanDays / s <= MAX_TICKS) ??
    TICK_STEPS_DAYS[TICK_STEPS_DAYS.length - 1];
  let date = ukToday(new Date(start));
  if (ukMidnight(date) < start) date = addDays(date, 1);
  const ticks: number[] = [];
  for (let t = ukMidnight(date); t <= end; t = ukMidnight(date)) {
    ticks.push(t);
    date = addDays(date, step);
  }
  return ticks;
}
