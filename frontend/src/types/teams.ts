import type { FolderMatchStatus, ScanStatus } from "@/lib/recordings";
import type { PlacementStatus } from "@/lib/register";
import type {
  HistoryState,
  TeamsChatMatch,
  TeamsWatchState,
} from "@/lib/teams";

export interface TeamsScanSummary {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: ScanStatus;
  chats_seen: number;
  chats_added: number;
  chats_matched: number;
  error_message: string | null;
}

export interface TeamsPlacement {
  id: string;
  consultant_name: string;
  client_name: string;
  project_name: string;
  start_date: string;
  expected_end_date: string | null;
  status: PlacementStatus;
}

export interface TeamsMember {
  oid: string;
  name: string;
}

export interface ParsedTitle {
  stack: string;
  consultant: string;
  client: string;
  start_date: string;
  end_date: string;
}

export interface TeamsChat {
  id: string;
  title: string;
  /** Null when the title could not be read (`error_message` says why). */
  parsed: ParsedTitle | null;
  /** The title as a quick add line, for "Create placement from title". */
  quick_add_line: string;
  match_status: TeamsChatMatch;
  placement: TeamsPlacement | null;
  candidates: TeamsPlacement[];
  watch_state: TeamsWatchState;
  watched_at: string | null;
  stopped_at: string | null;
  members: TeamsMember[];
  consultant_member: TeamsMember | null;
  consultant_member_match: FolderMatchStatus;
  last_message_at: string | null;
  history_state: HistoryState;
  error_message: string | null;
}

export interface TeamsChatList {
  chats: TeamsChat[];
  latest_scan: TeamsScanSummary | null;
  discovery_enabled: boolean;
  watching_enabled: boolean;
}
