import { describe, it, expect } from "vitest";
import {
  formatDuration,
  formatOffset,
  SESSION_KIND_LABELS,
  SESSION_KINDS,
  SPEAKER_ROLE_LABELS,
  SPEAKER_ROLES,
  speakerLabel,
} from "./sessions";

describe("formatOffset", () => {
  it("shows minutes and seconds, and hours past the hour", () => {
    expect(formatOffset(0)).toBe("0:00");
    expect(formatOffset(245_900)).toBe("4:05");
    expect(formatOffset(3_725_000)).toBe("1:02:05");
  });
});

describe("formatDuration", () => {
  it("rounds to minutes, with hours past the hour, and a dash when unknown", () => {
    expect(formatDuration(1_200)).toBe("20 min");
    expect(formatDuration(3_900)).toBe("1 h 5 min");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("speakerLabel", () => {
  it("names the speaker with their role, or the role alone, or the label", () => {
    const speakers = {
      A: { role: "consultant" as const, name: "Priya" },
      B: { role: "sme" as const, name: null },
    };
    expect(speakerLabel("A", speakers)).toBe("Priya (Consultant)");
    expect(speakerLabel("B", speakers)).toBe("PMO SME");
    expect(speakerLabel("C", speakers)).toBe("Speaker C");
  });
});

describe("labels", () => {
  it("has a label for every kind and every speaker role", () => {
    expect(Object.keys(SESSION_KIND_LABELS).sort()).toEqual(
      [...SESSION_KINDS].sort(),
    );
    expect(Object.keys(SPEAKER_ROLE_LABELS).sort()).toEqual(
      [...SPEAKER_ROLES].sort(),
    );
  });
});
