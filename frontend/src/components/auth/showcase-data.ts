import type { FlagSummary, EvidenceSignal, RiskBoardRow } from "@/types/health";

// Made-up placements for the sign-in page's preview. Nobody here is real, and
// the page says so ("Sample data"). Nothing is fetched before sign-in, and the
// values are fixed (no clock), so the preview is the same for every visitor.

export type SampleRow = Pick<
  RiskBoardRow,
  | "placement_id"
  | "consultant"
  | "client"
  | "overall"
  | "risk_level"
  | "trend"
  | "trend_delta"
  | "days_since_last_call"
>;

export const SAMPLE_ROWS: SampleRow[] = [
  {
    placement_id: "sample-1",
    consultant: { id: "sample-c1", name: "Aisha Rahman" },
    client: { id: "sample-k1", name: "Fabrikam" },
    overall: 4.1,
    risk_level: "red",
    trend: "down",
    trend_delta: -1.6,
    days_since_last_call: 3,
  },
  {
    placement_id: "sample-2",
    consultant: { id: "sample-c2", name: "Daniel Okafor" },
    client: { id: "sample-k2", name: "Litware" },
    overall: 4.6,
    risk_level: "red",
    trend: "down",
    trend_delta: -0.8,
    days_since_last_call: 3,
  },
  {
    placement_id: "sample-3",
    consultant: { id: "sample-c3", name: "Mei Chen" },
    client: { id: "sample-k3", name: "Adatum" },
    overall: 6.8,
    risk_level: "amber",
    trend: "down",
    trend_delta: -0.3,
    days_since_last_call: 3,
  },
];

export type SampleFlag = Pick<FlagSummary, "trigger" | "severity"> &
  Pick<EvidenceSignal, "quote" | "occurred_at">;

export const SAMPLE_FLAG: SampleFlag = {
  trigger: "client_dissatisfaction",
  severity: "critical",
  quote: "Their lead said they're losing confidence in the timeline.",
  // 14:32 on 12 Sep 2026, UK time (BST).
  occurred_at: "2026-09-12T13:32:00Z",
};
