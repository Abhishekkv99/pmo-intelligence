import type { TeamsChat, TeamsChatList } from "@/types/teams";

/** Mirrors `TeamsChatMatch` in backend/app/models/enums.py. */
export const TEAMS_CHAT_MATCHES = [
  "matched",
  "chosen",
  "needs_choice",
  "unmatched",
  "unparsed",
] as const;
export type TeamsChatMatch = (typeof TEAMS_CHAT_MATCHES)[number];

/** Mirrors `TeamsWatchState`. */
export const TEAMS_WATCH_STATES = [
  "not_watched",
  "watching",
  "stopped",
  "failed",
] as const;
export type TeamsWatchState = (typeof TEAMS_WATCH_STATES)[number];

/** Mirrors `HistoryState`. */
export const HISTORY_STATES = [
  "none",
  "stored",
  "analysing",
  "analysed",
] as const;
export type HistoryState = (typeof HISTORY_STATES)[number];

export const MATCH_LABELS: Record<TeamsChatMatch, string> = {
  matched: "Matched",
  chosen: "Chosen",
  needs_choice: "Several placements",
  unmatched: "No placement",
  unparsed: "Title not read",
};

export const WATCH_LABELS: Record<TeamsWatchState, string> = {
  not_watched: "Not watched",
  watching: "Watching",
  stopped: "Stopped",
  failed: "Failed",
};

export const HISTORY_LABELS: Record<HistoryState, string> = {
  none: "Not read",
  stored: "Stored",
  analysing: "Analysing",
  analysed: "Analysed",
};

/** Tied to a placement, by discovery or by a person. */
export function isLinked(chat: TeamsChat): boolean {
  return chat.match_status === "matched" || chat.match_status === "chosen";
}

/**
 * What a person has to settle on a chat, or null: a placement for a chat
 * that has none, or the consultant among the members of a watched chat.
 */
export function needsPerson(
  chat: TeamsChat,
): "placement" | "consultant" | null {
  if (!isLinked(chat)) return "placement";
  if (
    chat.watch_state === "watching" &&
    (chat.consultant_member_match === "needs_choice" ||
      chat.consultant_member_match === "unmatched")
  ) {
    return "consultant";
  }
  return null;
}

/** The chats waiting for a person, those needing a placement first. */
export function chatsNeedingPerson(chats: TeamsChat[]): TeamsChat[] {
  const placement = chats.filter((c) => needsPerson(c) === "placement");
  const consultant = chats.filter((c) => needsPerson(c) === "consultant");
  return [...placement, ...consultant];
}

// While a discovery pass runs the tab follows it closely; otherwise it only
// picks up the daily pass and the watch reviews.
export const BUSY_POLL_INTERVAL_MS = 10_000;
export const IDLE_POLL_INTERVAL_MS = 60_000;

export function pollInterval(list: TeamsChatList | undefined): number {
  return list?.latest_scan?.status === "running"
    ? BUSY_POLL_INTERVAL_MS
    : IDLE_POLL_INTERVAL_MS;
}

/** A placement as one line: consultant · client / project, dates. */
export function placementLabel(p: {
  consultant_name: string;
  client_name: string;
  project_name: string;
  start_date: string;
  expected_end_date: string | null;
}): string {
  const end = p.expected_end_date ?? "open";
  return `${p.consultant_name} · ${p.client_name} / ${p.project_name} (${p.start_date} to ${end})`;
}
