import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError } from "@/lib/api";
import type { SessionDetail } from "@/types/sessions";

const mockUseAuth = vi.fn();
const retrySession = vi.fn();
const setSessionKind = vi.fn();
const mutate = vi.fn();
let state: { session: SessionDetail | null; error: unknown } = {
  session: null,
  error: null,
};

vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));
vi.mock("@/hooks/useSessions", () => ({
  useSession: () => ({ ...state, isLoading: false, mutate }),
  useMediaUrl: () => ({
    media: {
      url: "https://bucket.example/call.webm",
      content_type: "audio/webm",
      expires_in_seconds: 900,
    },
    error: null,
    refresh: vi.fn(),
  }),
  retrySession: (...args: unknown[]) => retrySession(...args),
  setSessionKind: (...args: unknown[]) => setSessionKind(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SessionView } from "./SessionView";

function detail(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: "s1",
    placement_id: "p1",
    consultant: { id: "c1", name: "Priya Shah" },
    client: { id: "cl1", name: "Acme" },
    project: { id: "pr1", name: "Data platform" },
    held_at: "2026-10-01T09:00:00Z",
    duration_seconds: 1_200,
    kind: "technical",
    kind_overridden: false,
    session_class: "technical",
    project_phase: "first month",
    source: "upload",
    original_filename: "call.webm",
    status: "completed",
    error_message: null,
    quotes_rejected: 1,
    has_recording: true,
    summary: "Priya is blocked on VPN access.",
    speakers: {
      A: { role: "sme", name: "Sam" },
      B: { role: "consultant", name: "Priya" },
    },
    utterances: [
      { speaker: "A", text: "How is it going?", start_ms: 0, end_ms: 2_000 },
      {
        speaker: "B",
        text: "Still blocked on VPN access.",
        start_ms: 65_000,
        end_ms: 68_000,
      },
    ],
    signals: [
      {
        id: "g1",
        category: "issue",
        dimension: "onboarding",
        polarity: "negative",
        severity: 2,
        confidence: 0.9,
        quote: "Still blocked on VPN access.",
        note: "Access missing a month in.",
        speaker_role: "consultant",
        offset_ms: 65_000,
        issue_id: "i1",
      },
    ],
    issues: [
      {
        id: "i1",
        topic: "VPN access",
        status: "open",
        occurrence_count: 2,
        first_seen_at: "2026-09-20T09:00:00Z",
        last_seen_at: "2026-10-01T09:00:00Z",
        resolved_at: null,
        offset_ms: 65_000,
      },
    ],
    actions: [
      {
        id: "a1",
        description: "Chase the VPN",
        owner_role: "sme",
        owner: { id: "u1", full_name: "Sam Okafor", email: "sam@example.com" },
        quote: "How is it going?",
        offset_ms: 0,
        due_text: "today",
        due_date: "2026-10-01",
        status: "open",
        closed_at: null,
      },
    ],
    closed_actions: [],
    cost: { transcription_usd: 0.08, analysis_usd: 0.01, total_usd: 0.09 },
    node_errors: [{ node: "client_signals", error: "Timed out after 240 s" }],
    ...overrides,
  };
}

function signedInAs(role: string) {
  mockUseAuth.mockReturnValue({ user: { id: "me", role } });
}

describe("SessionView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state = { session: detail(), error: null };
    signedInAs("pmo_manager");
    // jsdom has no media playback.
    window.HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  });

  it("shows the call, summary, signals, issues, actions, cost and transcript", () => {
    render(<SessionView sessionId="s1" />);

    expect(
      screen.getByRole("heading", { name: "Priya Shah" }),
    ).toBeInTheDocument();
    // The client · project line opens the placement page.
    expect(
      screen.getByRole("link", { name: "Acme · Data platform" }),
    ).toHaveAttribute("href", "/placements/p1");
    expect(
      screen.getByText("Priya is blocked on VPN access."),
    ).toBeInTheDocument();
    const signal = screen.getByTestId("signal");
    expect(
      within(signal).getByText(/Still blocked on VPN/),
    ).toBeInTheDocument();
    expect(within(signal).getByText(/said by Consultant/)).toBeInTheDocument();
    expect(screen.getByTestId("issue")).toHaveTextContent("seen in 2 calls");
    expect(screen.getByTestId("action")).toHaveTextContent("Owner: Sam Okafor");
    expect(screen.getByTestId("session-cost")).toHaveTextContent("$0.09");
    expect(screen.getByText("Sam (PMO SME)")).toBeInTheDocument();
    expect(screen.getByText(/1 item\(s\) dropped/)).toBeInTheDocument();
    expect(screen.getByTestId("session-audio")).toHaveAttribute(
      "src",
      "https://bucket.example/call.webm",
    );
  });

  it("plays the recording from where a quote was said", async () => {
    const user = userEvent.setup();
    render(<SessionView sessionId="s1" />);
    const audio = screen.getByTestId("session-audio") as HTMLAudioElement;

    await user.click(
      within(screen.getByTestId("signal")).getByRole("button", {
        name: "Play from 1:05",
      }),
    );

    expect(audio.currentTime).toBe(65);
    expect(audio.play).toHaveBeenCalled();
  });

  it("shows the node errors and the kind picker to a PMO manager", () => {
    render(<SessionView sessionId="s1" />);

    expect(screen.getByTestId("node-errors")).toHaveTextContent(
      "Client signals: Timed out after 240 s",
    );
    expect(
      screen.getByRole("combobox", { name: "Kind of call" }),
    ).toBeInTheDocument();
  });

  it("shows neither to a placement specialist", () => {
    signedInAs("ps");
    state = { session: detail({ node_errors: null }), error: null };
    render(<SessionView sessionId="s1" />);

    expect(screen.queryByTestId("node-errors")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Kind of call" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Technical help")).toBeInTheDocument();
  });

  it("offers retry on a failed session to a PMO manager", async () => {
    const user = userEvent.setup();
    retrySession.mockResolvedValue({ id: "s1", status: "transcribed" });
    state = {
      session: detail({ status: "failed", error_message: "Analysis failed" }),
      error: null,
    };
    render(<SessionView sessionId="s1" />);

    expect(screen.getByRole("alert")).toHaveTextContent("Analysis failed");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(retrySession).toHaveBeenCalledWith("s1");
    expect(mutate).toHaveBeenCalled();
  });

  it("does not offer retry to anyone else", () => {
    signedInAs("sme");
    state = { session: detail({ status: "failed" }), error: null };
    render(<SessionView sessionId="s1" />);

    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
  });

  it("says when a call is still being processed", () => {
    state = {
      session: detail({
        status: "transcribing",
        summary: null,
        signals: [],
        has_recording: false,
      }),
      error: null,
    };
    render(<SessionView sessionId="s1" />);

    expect(screen.getByTestId("in-flight")).toBeInTheDocument();
    expect(screen.getByText("Not analysed yet.")).toBeInTheDocument();
    expect(screen.queryByTestId("session-audio")).not.toBeInTheDocument();
  });

  it("shows not found for a 404, in or out of scope alike", () => {
    state = { session: null, error: new ApiError("Not found", 404) };
    render(<SessionView sessionId="s1" />);

    expect(screen.getByText("Session not found")).toBeInTheDocument();
  });
});
