import type { PlacementStatus } from "@/lib/register";
import type {
  FolderMatchStatus,
  ScanStatus,
  SessionSource,
  SessionStatus,
} from "@/lib/recordings";

export interface ConsultantRef {
  id: string;
  full_name: string;
}

export interface RecordingSessionRef {
  id: string;
  status: SessionStatus;
  error_message: string | null;
}

export interface RecordingItem {
  id: string;
  filename: string;
  size_bytes: number;
  /** From the file name; the S3 time when `time_from_name` is false. */
  recorded_at: string;
  time_from_name: boolean;
  estimated_minutes: number;
  estimated_cost_usd: number;
  session: RecordingSessionRef | null;
}

export interface RecordingFolder {
  id: string;
  display_name: string;
  folder_date: string | null;
  match_status: FolderMatchStatus;
  consultant: ConsultantRef | null;
  candidates: ConsultantRef[];
  last_seen_at: string;
  recordings: RecordingItem[];
}

export interface ScanSummary {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: ScanStatus;
  folders_seen: number;
  folders_added: number;
  folders_matched: number;
  recordings_seen: number;
  recordings_added: number;
  error_message: string | null;
}

export interface RecordingFolderList {
  folders: RecordingFolder[];
  latest_scan: ScanSummary | null;
  scan_enabled: boolean;
  scan_interval_seconds: number;
}

export interface PlacementOption {
  id: string;
  client_name: string;
  project_name: string;
  start_date: string;
  expected_end_date: string | null;
  status: PlacementStatus;
}

/** The 409 body of Process when a placement must be chosen. */
export interface PlacementChoice {
  detail: string;
  placements: PlacementOption[];
}

export interface SessionCreated {
  id: string;
  placement_id: string;
  source: SessionSource;
  status: SessionStatus;
  held_at: string;
}
