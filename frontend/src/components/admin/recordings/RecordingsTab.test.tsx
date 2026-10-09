import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { RecordingFolder, RecordingFolderList } from "@/types/recordings";

const mutate = vi.fn();
const processRecording = vi.fn();
const requestScan = vi.fn();
const success = vi.fn();
let list: RecordingFolderList | null = null;

vi.mock("@/hooks/useRecordings", () => ({
  useRecordings: () => ({ list, isLoading: false, error: null, mutate }),
  processRecording: (...args: unknown[]) => processRecording(...args),
  requestScan: () => requestScan(),
  chooseFolderConsultant: vi.fn(),
}));
vi.mock("@/hooks/useRegister", () => ({
  useConsultants: () => ({ items: [] }),
  usePlacements: () => ({ items: [] }),
}));
vi.mock("sonner", () => ({
  toast: { success: (m: string) => success(m), error: vi.fn() },
}));

import { RecordingsTab } from "./RecordingsTab";

const annFolder: RecordingFolder = {
  id: "f1",
  display_name: "14-09-26 - PMO support Ann",
  folder_date: "2026-09-14",
  match_status: "matched",
  consultant: { id: "c1", full_name: "Ann Brooks" },
  candidates: [],
  last_seen_at: "2026-10-09T09:00:00Z",
  recordings: [
    {
      id: "r1",
      filename: "Recording 2026-10-01 10-00-00.webm",
      size_bytes: 131_000_000,
      recorded_at: "2026-10-01T09:00:00Z",
      time_from_name: true,
      estimated_minutes: 27.6,
      estimated_cost_usd: 0.11,
      session: null,
    },
    {
      id: "r2",
      filename: "Recording 2026-09-20 10-00-00.webm",
      size_bytes: 90_000_000,
      recorded_at: "2026-09-20T09:00:00Z",
      time_from_name: true,
      estimated_minutes: 19,
      estimated_cost_usd: 0.07,
      session: { id: "s2", status: "failed", error_message: "no audio" },
    },
  ],
};

const priyaFolder: RecordingFolder = {
  id: "f2",
  display_name: "Priya check-in",
  folder_date: null,
  match_status: "needs_choice",
  consultant: null,
  candidates: [
    { id: "c2", full_name: "Priya Shah" },
    { id: "c3", full_name: "Priya Patel" },
  ],
  last_seen_at: "2026-10-09T09:00:00Z",
  recordings: [
    {
      id: "r3",
      filename: "Mani 2.webm",
      size_bytes: 60_000_000,
      recorded_at: "2026-09-05T09:00:00Z",
      time_from_name: false,
      estimated_minutes: 12.7,
      estimated_cost_usd: 0.05,
      session: null,
    },
  ],
};

function listOf(folders: RecordingFolder[]): RecordingFolderList {
  return {
    folders,
    latest_scan: {
      id: "scan1",
      started_at: "2026-10-09T08:56:46Z",
      finished_at: "2026-10-09T08:56:49Z",
      status: "completed",
      folders_seen: 49,
      folders_added: 49,
      folders_matched: 0,
      recordings_seen: 208,
      recordings_added: 208,
      error_message: null,
    },
    scan_enabled: true,
    scan_interval_seconds: 900,
  };
}

describe("RecordingsTab", () => {
  beforeEach(() => {
    list = listOf([annFolder, priyaFolder]);
    mutate.mockReset();
    processRecording.mockReset();
    requestScan.mockReset();
    success.mockReset();
  });

  it("summarises the last scan and the schedule", () => {
    render(<RecordingsTab enabled />);

    expect(
      screen.getByText(/49 folders, 208 recordings \(208 new\)/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Scanned automatically every 15 minutes/),
    ).toBeInTheDocument();
  });

  it("lists folders that need a choice with their candidates", () => {
    render(<RecordingsTab enabled />);

    expect(
      screen.getByText("Could be Priya Shah or Priya Patel · 1 recordings"),
    ).toBeInTheDocument();
  });

  it("lists recordings newest first with status and estimate", () => {
    render(<RecordingsTab enabled />);

    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("1 Oct 2026, 10:00")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Not processed")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText(/about 28 min, \$0\.11/),
    ).toBeInTheDocument();
    const failed = within(rows[1]).getByText("Failed");
    expect(failed).toHaveAttribute("title", "no audio");
    // A processed recording opens its session page.
    expect(
      within(rows[1]).getByRole("link", { name: "Open the session (Failed)" }),
    ).toHaveAttribute("href", "/sessions/s2");
    expect(
      within(rows[1]).queryByRole("button", { name: "Process" }),
    ).toBeNull();
    expect(
      within(rows[2]).getByText("file time, not in the name"),
    ).toBeInTheDocument();
  });

  it("keeps Process off until the folder has a consultant", () => {
    render(<RecordingsTab enabled />);

    const rows = screen.getAllByRole("row").slice(1);
    expect(
      within(rows[0]).getByRole("button", { name: "Process" }),
    ).toBeEnabled();
    expect(
      within(rows[2]).getByRole("button", { name: "Process" }),
    ).toBeDisabled();
  });

  it("processes after confirming the estimated cost", async () => {
    processRecording.mockResolvedValue({ kind: "queued", session: {} });
    render(<RecordingsTab enabled />);

    const rows = screen.getAllByRole("row").slice(1);
    await userEvent.click(
      within(rows[0]).getByRole("button", { name: "Process" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("$0.11")).toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Process" }),
    );

    expect(processRecording).toHaveBeenCalledWith("r1", null);
    expect(success).toHaveBeenCalledWith("Queued for transcription");
    expect(mutate).toHaveBeenCalled();
  });

  it("asks for a placement when the API offers a choice", async () => {
    processRecording.mockResolvedValue({
      kind: "choose",
      choice: {
        detail:
          "More than one placement of this consultant covers 2026-10-01; choose the placement",
        placements: [
          {
            id: "p1",
            client_name: "Northwind",
            project_name: "Data platform",
            start_date: "2026-09-01",
            expected_end_date: null,
            status: "active",
          },
        ],
      },
    });
    render(<RecordingsTab enabled />);

    const rows = screen.getAllByRole("row").slice(1);
    await userEvent.click(
      within(rows[0]).getByRole("button", { name: "Process" }),
    );
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Process" }),
    );

    expect(
      within(dialog).getByText(/More than one placement/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", {
        name: "Process with this placement",
      }),
    ).toBeDisabled();
    expect(success).not.toHaveBeenCalled();
  });

  it("asks for a scan and says when one is already queued", async () => {
    requestScan.mockResolvedValue({ queued: false });
    render(<RecordingsTab enabled />);

    await userEvent.click(screen.getByRole("button", { name: /Scan now/ }));

    expect(success).toHaveBeenCalledWith("A scan is already queued or running");
  });

  it("shows why the last scan failed", () => {
    const failing = listOf([]);
    failing.latest_scan = {
      ...failing.latest_scan!,
      status: "failed",
      error_message: "ClientError: AccessDenied",
    };
    list = failing;
    render(<RecordingsTab enabled />);

    expect(
      screen.getByText(/Last scan failed at .*AccessDenied/),
    ).toBeInTheDocument();
  });
});
