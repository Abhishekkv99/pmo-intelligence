import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProcessingStatusPanel, formatRss } from "./ProcessingStatusPanel";
import type { ProcessingStatusResponse } from "@/types/processing";

const mockUseProcessingStatus = vi.fn();

vi.mock("@/hooks/useProcessingStatus", () => ({
  useProcessingStatus: (enabled: boolean) => mockUseProcessingStatus(enabled),
}));

function makeStatus(
  overrides: Partial<ProcessingStatusResponse> = {},
): ProcessingStatusResponse {
  return {
    queue_depth: 0,
    capacity: 1,
    running: [],
    rss_mib: 412.4,
    memory_diagnostics_enabled: false,
    ...overrides,
  };
}

function mockStatus(
  status: ProcessingStatusResponse | null,
  extra: Partial<{ isLoading: boolean; error: string | null }> = {},
) {
  mockUseProcessingStatus.mockReturnValue({
    status,
    isBusy: status
      ? status.queue_depth > 0 || status.running.length > 0
      : false,
    isLoading: false,
    error: null,
    mutate: vi.fn(),
    ...extra,
  });
}

describe("formatRss", () => {
  it("rounds to whole MiB and labels a missing reading", () => {
    expect(formatRss(412.4)).toBe("412 MiB");
    expect(formatRss(511.6)).toBe("512 MiB");
    expect(formatRss(null)).toBe("n/a");
  });
});

describe("ProcessingStatusPanel", () => {
  beforeEach(() => {
    mockUseProcessingStatus.mockReset();
  });

  it("renders nothing and passes enabled=false to the hook for a non-global user", () => {
    mockStatus(null);
    render(<ProcessingStatusPanel enabled={false} />);
    expect(mockUseProcessingStatus).toHaveBeenCalledWith(false);
    expect(
      screen.queryByTestId("processing-status-panel"),
    ).not.toBeInTheDocument();
  });

  it("shows depth, running-of-capacity and memory for an idle queue", () => {
    mockStatus(makeStatus());
    render(<ProcessingStatusPanel enabled />);
    expect(mockUseProcessingStatus).toHaveBeenCalledWith(true);
    expect(screen.getByTestId("queue-depth")).toHaveTextContent("0");
    expect(screen.getByTestId("queue-running")).toHaveTextContent("0 of 1");
    expect(screen.getByTestId("queue-rss")).toHaveTextContent("412 MiB");
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.getByText("Nothing is running.")).toBeInTheDocument();
    expect(
      screen.getByText("Auto-refreshing every 30 seconds."),
    ).toBeInTheDocument();
  });

  it("lists running jobs by kind and short id, without links", () => {
    mockStatus(
      makeStatus({
        queue_depth: 12,
        running: [
          {
            kind: "chat",
            id: "aaaaaaaa-1111-2222-3333-444444444444",
            started_at: "2026-09-21T20:15:00Z",
            worker: 0,
          },
          {
            kind: "session",
            id: "bbbbbbbb-1111-2222-3333-444444444444",
            started_at: "2026-09-21T20:16:00Z",
            worker: 1,
          },
        ],
      }),
    );
    render(<ProcessingStatusPanel enabled />);
    expect(screen.getByTestId("queue-depth")).toHaveTextContent("12");
    expect(screen.getByText("Busy")).toBeInTheDocument();
    expect(screen.getByText("chat")).toBeInTheDocument();
    expect(screen.getByText("session")).toBeInTheDocument();
    expect(screen.getByText("aaaaaaaa")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbbb")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.getByText("Auto-refreshing every 5 seconds..."),
    ).toBeInTheDocument();
  });

  it("shows n/a when the backend cannot read its memory and notes diagnostics", () => {
    mockStatus(makeStatus({ rss_mib: null, memory_diagnostics_enabled: true }));
    render(<ProcessingStatusPanel enabled />);
    expect(screen.getByTestId("queue-rss")).toHaveTextContent("n/a");
    expect(screen.getByText(/Memory diagnostics are on/)).toBeInTheDocument();
  });

  it("shows the error when the status request fails", () => {
    mockStatus(null, { error: "Not authorised for this operation" });
    render(<ProcessingStatusPanel enabled />);
    expect(
      screen.getByText(
        "Failed to load processing status: Not authorised for this operation",
      ),
    ).toBeInTheDocument();
  });
});
