import type { Role } from "@/lib/roles";
import type {
  ConsultantStatus,
  ExtensionStatus,
  PlacementStatus,
} from "@/lib/register";

/** A user named on a project or placement (tech lead, PS, SME). */
export interface PersonRef {
  id: string;
  full_name: string;
  email: string;
}

export interface Consultant {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  skills: string[];
  status: ConsultantStatus;
  created_at: string;
  updated_at: string;
}

export interface Client {
  id: string;
  name: string;
  industry: string | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  client_id: string;
  client_name: string;
  name: string;
  client_manager_name: string | null;
  tech_lead: PersonRef | null;
  start_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface Placement {
  id: string;
  consultant: { id: string; full_name: string; email: string | null };
  client: { id: string; name: string };
  project: { id: string; name: string };
  start_date: string;
  expected_end_date: string | null;
  extension_status: ExtensionStatus;
  rate_band: string | null;
  /** The consultant's stack on this engagement, e.g. DS. */
  stack: string | null;
  status: PlacementStatus;
  ended_reason: string | null;
  ps: PersonRef | null;
  sme: PersonRef | null;
  tech_lead: PersonRef | null;
  created_at: string;
  updated_at: string;
}

export interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: Role | null;
  is_active: boolean;
  /** False until the user's first sign-in links the Microsoft account. */
  signed_in_with_microsoft: boolean;
}

export type QuickAddOutcome = "create" | "update" | "unchanged" | "error";

export interface QuickAddLineResult {
  /** Position among the lines sent, from 1. */
  line: number;
  text: string;
  outcome: QuickAddOutcome;
  stack: string | null;
  consultant: string | null;
  client: string | null;
  start_date: string | null;
  expected_end_date: string | null;
  changes: string[];
  errors: string[];
}

export interface QuickAddResult {
  dry_run: boolean;
  /** True only when this call wrote the lines: a Confirm with no line errors. */
  applied: boolean;
  summary: {
    lines: number;
    created: number;
    updated: number;
    unchanged: number;
    errors: number;
  };
  lines: QuickAddLineResult[];
}
