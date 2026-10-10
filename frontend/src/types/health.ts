import type {
  FlagSeverity,
  HealthView,
  RiskLevel,
  RiskTrigger,
  Trend,
} from "@/lib/health";
import type { SpeakerRole } from "@/lib/sessions";
import type { NamedRef } from "@/types/sessions";

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
  tech_lead: PersonView | null;
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
