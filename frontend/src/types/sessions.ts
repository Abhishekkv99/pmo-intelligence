import type { SessionSource, SessionStatus } from "@/lib/recordings";
import type {
  ActionStatus,
  Dimension,
  IssueStatus,
  Polarity,
  SessionKind,
  SignalCategory,
  SpeakerRole,
} from "@/lib/sessions";

export interface NamedRef {
  id: string;
  name: string;
}

export interface SessionListItem {
  id: string;
  placement_id: string;
  consultant: NamedRef;
  client: NamedRef;
  project: NamedRef;
  held_at: string;
  duration_seconds: number | null;
  kind: SessionKind | null;
  status: SessionStatus;
  error_message: string | null;
  signal_count: number;
  action_count: number;
}

export interface SpeakerView {
  role: SpeakerRole;
  name: string | null;
}

export interface UtteranceView {
  speaker: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface SignalView {
  id: string;
  category: SignalCategory;
  dimension: Dimension;
  polarity: Polarity;
  severity: number;
  confidence: number;
  quote: string;
  note: string | null;
  speaker_role: SpeakerRole | null;
  offset_ms: number | null;
  issue_id: string | null;
}

export interface IssueView {
  id: string;
  topic: string;
  status: IssueStatus;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  /** Where this call first talks about it. */
  offset_ms: number | null;
}

export interface PersonView {
  id: string;
  full_name: string | null;
  email: string;
}

export interface ActionView {
  id: string;
  description: string;
  owner_role: SpeakerRole;
  owner: PersonView | null;
  quote: string;
  offset_ms: number | null;
  due_text: string | null;
  due_date: string | null;
  status: ActionStatus;
  closed_at: string | null;
}

export interface NodeError {
  node: string;
  error: string;
  [key: string]: unknown;
}

export interface SessionDetail {
  id: string;
  placement_id: string;
  consultant: NamedRef;
  client: NamedRef;
  project: NamedRef;
  held_at: string;
  duration_seconds: number | null;
  kind: SessionKind | null;
  kind_overridden: boolean;
  /** What the pipeline classified the call as, whatever the kind in use. */
  session_class: SessionKind | null;
  project_phase: string | null;
  source: SessionSource;
  original_filename: string | null;
  status: SessionStatus;
  error_message: string | null;
  quotes_rejected: number;
  has_recording: boolean;
  summary: string | null;
  speakers: Record<string, SpeakerView>;
  utterances: UtteranceView[];
  signals: SignalView[];
  issues: IssueView[];
  actions: ActionView[];
  /** Earlier actions this call said were done. */
  closed_actions: ActionView[];
  cost: { transcription_usd: number; analysis_usd: number; total_usd: number };
  /** For the global roles only; null for everyone else. */
  node_errors: NodeError[] | null;
}

export interface MediaUrl {
  url: string;
  content_type: string;
  expires_in_seconds: number;
}
