/**
 * Recordings and sessions in the UI. The enumerations mirror `FolderMatchStatus`,
 * `ScanStatus`, `SessionSource` and `SessionStatus` in
 * `backend/app/models/enums.py`, the single source for these values; keep the
 * two in step.
 */
import type { RecordingFolder, RecordingItem } from "@/types/recordings";

export const FOLDER_MATCH_STATUSES = [
  "matched",
  "chosen",
  "needs_choice",
  "unmatched",
] as const;
export type FolderMatchStatus = (typeof FOLDER_MATCH_STATUSES)[number];

export const SCAN_STATUSES = ["running", "completed", "failed"] as const;
export type ScanStatus = (typeof SCAN_STATUSES)[number];

export const SESSION_SOURCES = ["s3", "upload", "url", "graph"] as const;
export type SessionSource = (typeof SESSION_SOURCES)[number];

export const SESSION_STATUSES = [
  "uploaded",
  "transcribing",
  "transcribed",
  "analyzing",
  "completed",
  "failed",
] as const;
export type SessionStatus = (typeof SESSION_STATUSES)[number];

/**
 * Statuses a session passes through while its job still has work to do;
 * `transcribed` is waiting for its analysis.
 */
const IN_FLIGHT: ReadonlySet<SessionStatus> = new Set([
  "uploaded",
  "transcribing",
  "transcribed",
  "analyzing",
]);

export function isInFlight(status: SessionStatus): boolean {
  return IN_FLIGHT.has(status);
}

/** Every recording with the folder it sits in, newest call first. */
export interface RecordingRow {
  recording: RecordingItem;
  folder: RecordingFolder;
}

export function recordingRows(folders: RecordingFolder[]): RecordingRow[] {
  return folders
    .flatMap((folder) =>
      folder.recordings.map((recording) => ({ recording, folder })),
    )
    .sort((a, b) =>
      b.recording.recorded_at.localeCompare(a.recording.recorded_at),
    );
}

export function anyInFlight(folders: RecordingFolder[]): boolean {
  return folders.some((f) =>
    f.recordings.some((r) => r.session && isInFlight(r.session.status)),
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
}

export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

// --- UK time ------------------------------------------------------------------
//
// Calls are held in the UK, and the forms take the time as the person would
// read it on a UK clock, whatever the browser's own time zone.

const UK_TIME_ZONE = "Europe/London";

const ukParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** Minutes the UK clock is ahead of UTC at the instant `utcMs`. */
function ukOffsetMinutes(utcMs: number): number {
  const parts = Object.fromEntries(
    ukParts.formatToParts(new Date(utcMs)).map((p) => [p.type, p.value]),
  );
  const asUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  return Math.round((asUtc - utcMs) / 60000);
}

/**
 * A `datetime-local` value ("2026-10-01T10:00") read as UK time, as ISO 8601
 * with its offset ("2026-10-01T10:00:00+01:00"), which is what the API takes.
 */
export function ukLocalToIso(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error(`Not a date and time: ${value}`);
  const [, y, mo, d, h, mi] = match.map(Number);
  const wallAsUtc = Date.UTC(y, mo - 1, d, h, mi);
  // The offset at the wall time itself, found by stepping once from a guess.
  const offset = ukOffsetMinutes(
    wallAsUtc - ukOffsetMinutes(wallAsUtc) * 60000,
  );
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `${value}:00${sign}${hh}:${mm}`;
}

/** An instant as shown on the page: "1 Oct 2026, 10:00" on a UK clock. */
export function formatUkDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: UK_TIME_ZONE,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}

/**
 * The call time in a Talk-style file name, as a `datetime-local` value, to
 * prefill the form: "Recording 2026-10-01 10-00-00.webm" and
 * "V1_2026-10-01T100000.mp4". Null when the name carries none.
 */
export function heldAtFromFilename(filename: string): string | null {
  const talk = /^Recording (\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-\d{2}\./.exec(
    filename,
  );
  if (talk) return `${talk[1]}T${talk[2]}:${talk[3]}`;
  const versioned = /^V\d+_(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})\d{2}\./.exec(
    filename,
  );
  if (versioned) return `${versioned[1]}T${versioned[2]}:${versioned[3]}`;
  return null;
}
