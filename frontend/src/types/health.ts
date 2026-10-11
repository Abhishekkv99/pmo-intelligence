import type {
  FlagSeverity,
  HealthView,
  RiskLevel,
  RiskTrigger,
  SignalIndicator,
  SnapshotReason,
  SourceKind,
  Trend,
} from "@/lib/health";
import type { SessionStatus } from "@/lib/recordings";
import type { ExtensionStatus, PlacementStatus } from "@/lib/register";
import type {
  Dimension,
  IssueStatus,
  Polarity,
  SessionKind,
  SpeakerRole,
} from "@/lib/sessions";
import type { ActionView, NamedRef } from "@/types/sessions";

export interface PersonView {
  id: string;
  full_name: string | null;
  email: string;
}

export interface FlagSummary {
  id: string;
  trigger: RiskTrigger;
  severity: FlagSeverity;
  opened_at: string;
}

export interface NextAction {
  id: string;
  description: string;
  owner_role: SpeakerRole;
  due_date: string;
}

/**
 * One active placement on the board (`GET /risk-board`). In the technical
 * view (an SME) `overall`, `risk_level`, `trend` and `trend_delta` are null
 * and `open_flags` is empty.
 */
export interface RiskBoardRow {
  placement_id: string;
  view: HealthView;
  consultant: NamedRef;
  client: NamedRef;
  project: NamedRef;
  ps: PersonView | null;
  /** The consultant's CDM. */
  cdm: PersonView | null;
  /** The placement's stack (DS), for the board's filter. */
  stack: string | null;
  start_date: string;
  weeks_in: number;
  /** False with no snapshot yet, or no signal in the lookback. */
  scored: boolean;
  computed_at: string | null;
  overall: number | null;
  risk_level: RiskLevel | null;
  trend: Trend | null;
  trend_delta: number | null;
  technical: number | null;
  technical_trend: Trend | null;
  technical_trend_delta: number | null;
  open_flags: FlagSummary[];
  last_call_at: string | null;
  days_since_last_call: number | null;
  next_action: NextAction | null;
}

/** The six scores; in the technical view only `technical` is set. */
export type DimensionScores = Record<Dimension, number | null>;

/** A signal shown as evidence, with where and when it was said. */
export interface EvidenceSignal {
  id: string;
  source_kind: SourceKind;
  /** The session (or message) it was said in. */
  source_id: string;
  dimension: Dimension;
  polarity: Polarity;
  severity: number;
  confidence: number;
  quote: string;
  note: string | null;
  speaker_role: SpeakerRole | null;
  occurred_at: string;
  offset_ms: number | null;
  indicator: SignalIndicator | null;
}

/** A signal that pulled a dimension's score, with the weight it had. */
export interface Contributor {
  signal: EvidenceSignal;
  weight: number;
  value: number;
}

export interface DimensionEvidence {
  dimension: Dimension;
  signal_count: number;
  /** Largest pull first. */
  contributors: Contributor[];
}

export interface SnapshotDetail {
  computed_at: string;
  reason: SnapshotReason;
  scored: boolean;
  scores: DimensionScores;
  overall: number | null;
  risk_level: RiskLevel | null;
  trend: Trend | null;
  trend_delta: number | null;
  technical_trend: Trend | null;
  technical_trend_delta: number | null;
  /** Null in the technical view. */
  signal_count: number | null;
  weights_version: string;
  evidence: DimensionEvidence[];
}

/** One point of the health chart. */
export interface SnapshotPoint {
  computed_at: string;
  reason: SnapshotReason;
  scored: boolean;
  scores: DimensionScores;
  overall: number | null;
  risk_level: RiskLevel | null;
  trend: Trend | null;
  technical_trend: Trend | null;
}

export interface FlagDetail {
  id: string;
  trigger: RiskTrigger;
  severity: FlagSeverity;
  opened_at: string;
  /** Newest said first; empty for a flag raised from the register. */
  evidence: EvidenceSignal[];
}

/** A call of the placement; a completed one is a marker on the chart. */
export interface PlacementSession {
  id: string;
  held_at: string;
  kind: SessionKind | null;
  status: SessionStatus;
  duration_seconds: number | null;
  /** Technical signals only in the technical view. */
  signal_count: number;
  action_count: number;
}

export interface OpenIssue {
  id: string;
  topic: string;
  status: IssueStatus;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

/** An action with the call or message it was agreed in. */
export interface PlacementAction extends ActionView {
  source_kind: SourceKind;
  source_id: string;
}

export interface RegisterFields {
  start_date: string;
  expected_end_date: string | null;
  status: PlacementStatus;
  stack: string | null;
  client_manager_name: string | null;
  ps: PersonView | null;
  sme: PersonView | null;
  /** The consultant's CDM. */
  cdm: PersonView | null;
  /** Null in the technical view: contract matters. */
  extension_status: ExtensionStatus | null;
  rate_band: string | null;
  ended_reason: string | null;
}

/** Another placement of the same consultant that the reader may see. */
export interface OtherPlacement {
  id: string;
  client: NamedRef;
  project: NamedRef;
  start_date: string;
  expected_end_date: string | null;
  status: PlacementStatus;
}

/** The RAG thresholds of the health configuration in use. */
export interface RagThresholds {
  green_from: number;
  amber_from: number;
}

/**
 * The placement (consultant) page (`GET /placements/{id}/health`). In the
 * technical view (an SME) only the Technical score, its trend and its
 * evidence are given, `open_flags` is empty and the register's contract
 * fields are null.
 */
export interface PlacementHealth {
  placement_id: string;
  view: HealthView;
  consultant: NamedRef;
  client: NamedRef;
  project: NamedRef;
  weeks_in: number;
  register_fields: RegisterFields;
  /** Null before the first recompute. */
  latest: SnapshotDetail | null;
  /** Every snapshot, oldest first. */
  history: SnapshotPoint[];
  open_flags: FlagDetail[];
  /** Newest call first. */
  sessions: PlacementSession[];
  /** Longest open first. */
  open_issues: OpenIssue[];
  /** Open and overdue first by due date, then done ones, newest closed first. */
  actions: PlacementAction[];
  /** Newest start first. */
  other_placements: OtherPlacement[];
  thresholds: RagThresholds;
}
