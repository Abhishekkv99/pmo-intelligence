import { describe, it, expect } from "vitest";
import type { RecordingFolder, RecordingItem } from "@/types/recordings";
import {
  anyInFlight,
  formatBytes,
  formatUkDateTime,
  formatUsd,
  heldAtFromFilename,
  isInFlight,
  recordingRows,
  ukLocalToIso,
  type SessionStatus,
} from "./recordings";

function recording(
  id: string,
  recordedAt: string,
  status: SessionStatus | null = null,
): RecordingItem {
  return {
    id,
    filename: `${id}.webm`,
    size_bytes: 131_000_000,
    recorded_at: recordedAt,
    time_from_name: true,
    estimated_minutes: 27.6,
    estimated_cost_usd: 0.11,
    session: status ? { id: `s-${id}`, status, error_message: null } : null,
  };
}

function folder(id: string, recordings: RecordingItem[]): RecordingFolder {
  return {
    id,
    display_name: id,
    folder_date: null,
    match_status: "matched",
    consultant: { id: "c1", full_name: "Ann Brooks" },
    candidates: [],
    last_seen_at: "2026-10-09T09:00:00Z",
    recordings,
  };
}

describe("ukLocalToIso", () => {
  it("reads a summer time as British Summer Time", () => {
    expect(ukLocalToIso("2026-10-01T10:00")).toBe("2026-10-01T10:00:00+01:00");
  });

  it("reads a winter time as GMT", () => {
    expect(ukLocalToIso("2026-12-01T10:00")).toBe("2026-12-01T10:00:00+00:00");
  });

  it("uses the offset of the day the clocks change, after the change", () => {
    // 25 October 2026: BST ends at 02:00; 10:00 that day is GMT.
    expect(ukLocalToIso("2026-10-25T10:00")).toBe("2026-10-25T10:00:00+00:00");
    // 29 March 2026: BST starts at 01:00; 10:00 that day is BST.
    expect(ukLocalToIso("2026-03-29T10:00")).toBe("2026-03-29T10:00:00+01:00");
  });

  it("refuses something that is not a date and time", () => {
    expect(() => ukLocalToIso("tomorrow")).toThrow();
  });
});

describe("formatUkDateTime", () => {
  it("shows an instant on a UK clock", () => {
    expect(formatUkDateTime("2026-10-01T09:00:00Z")).toBe("1 Oct 2026, 10:00");
  });
});

describe("heldAtFromFilename", () => {
  it("reads a Talk recording name", () => {
    expect(heldAtFromFilename("Recording 2026-10-01 10-05-33.webm")).toBe(
      "2026-10-01T10:05",
    );
  });

  it("reads a versioned recording name", () => {
    expect(heldAtFromFilename("V1_2026-07-15T143005.mp4")).toBe(
      "2026-07-15T14:30",
    );
  });

  it("gives nothing for a name without a time", () => {
    expect(heldAtFromFilename("check-in.webm")).toBeNull();
  });
});

describe("recordings in the table", () => {
  const folders = [
    folder("a", [recording("old", "2026-08-01T09:00:00Z")]),
    folder("b", [
      recording("new", "2026-10-01T09:00:00Z", "transcribing"),
      recording("mid", "2026-09-01T09:00:00Z", "failed"),
    ]),
  ];

  it("lists every recording with its folder, newest call first", () => {
    expect(
      recordingRows(folders).map((r) => [r.recording.id, r.folder.id]),
    ).toEqual([
      ["new", "b"],
      ["mid", "b"],
      ["old", "a"],
    ]);
  });

  it("is in flight while a session is waiting or transcribing", () => {
    expect(anyInFlight(folders)).toBe(true);
    expect(isInFlight("uploaded")).toBe(true);
    expect(isInFlight("transcribed")).toBe(false);
    expect(isInFlight("failed")).toBe(false);
    expect(
      anyInFlight([folder("a", [recording("x", "2026-10-01T09:00:00Z")])]),
    ).toBe(false);
  });

  it("formats sizes and costs", () => {
    expect(formatBytes(131_000_000)).toBe("125 MB");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatUsd(0.11)).toBe("$0.11");
  });
});
