/**
 * Sessions in the UI. The enumerations mirror `SessionKind`, `SpeakerRole`,
 * `Dimension`, `Polarity`, `SignalCategory`, `IssueStatus` and `ActionStatus`
 * in `backend/app/models/enums.py`, the single source for these values; keep
 * the two in step.
 */

export const SESSION_KINDS = [
  "onboarding",
  "technical",
  "check_in",
  "escalation",
  "other",
] as const;
export type SessionKind = (typeof SESSION_KINDS)[number];

export const SPEAKER_ROLES = [
  "consultant",
  "pmo_manager",
  "sme",
  "tech_lead",
  "ps",
  "other",
] as const;
export type SpeakerRole = (typeof SPEAKER_ROLES)[number];

export const DIMENSIONS = [
  "delivery",
  "technical",
  "relationship",
  "engagement",
  "onboarding",
  "communication",
] as const;
export type Dimension = (typeof DIMENSIONS)[number];

export const POLARITIES = ["positive", "negative", "neutral"] as const;
export type Polarity = (typeof POLARITIES)[number];

export const SIGNAL_CATEGORIES = [
  "issue",
  "relationship_engagement",
  "client",
] as const;
export type SignalCategory = (typeof SIGNAL_CATEGORIES)[number];

export const ISSUE_STATUSES = ["open", "resolved"] as const;
export type IssueStatus = (typeof ISSUE_STATUSES)[number];

export const ACTION_STATUSES = ["open", "done", "overdue"] as const;
export type ActionStatus = (typeof ACTION_STATUSES)[number];

export const SESSION_KIND_LABELS: Record<SessionKind, string> = {
  onboarding: "Onboarding",
  technical: "Technical help",
  check_in: "Check-in",
  escalation: "Escalation",
  other: "Other",
};

export const SPEAKER_ROLE_LABELS: Record<SpeakerRole, string> = {
  consultant: "Consultant",
  pmo_manager: "PMO manager",
  sme: "PMO SME",
  tech_lead: "Tech lead",
  ps: "Placement specialist",
  other: "Other",
};

/** A position in the recording: "4:05", or "1:02:05" past the hour. */
export function formatOffset(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}`
    : `${minutes}:${seconds}`;
}

/** A call's length: "20 min", or "1 h 5 min"; a dash before it is known. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** Who a diarized speaker label was, as the transcript shows it. */
export function speakerLabel(
  label: string,
  speakers: Record<string, { role: SpeakerRole; name: string | null }>,
): string {
  const speaker = speakers[label];
  if (!speaker) return `Speaker ${label}`;
  const role = SPEAKER_ROLE_LABELS[speaker.role];
  return speaker.name ? `${speaker.name} (${role})` : role;
}
