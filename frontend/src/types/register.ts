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

export type ImportOutcome = "create" | "update" | "unchanged" | "error";

export interface ImportRowResult {
  /** Line number in the file; the header is line 1. */
  row: number;
  outcome: ImportOutcome;
  consultant: string | null;
  client: string | null;
  project: string | null;
  changes: string[];
  warnings: string[];
  errors: string[];
}

export interface ImportResult {
  dry_run: boolean;
  /** True only when this call wrote the rows: a Confirm with no row errors. */
  applied: boolean;
  summary: {
    rows: number;
    created: number;
    updated: number;
    unchanged: number;
    errors: number;
  };
  rows: ImportRowResult[];
}
