"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import {
  callMarkers,
  chartDomain,
  chartPoints,
  chartTicks,
  formatScore,
  formatUkAxisDate,
  RISK_LEVEL_LABELS,
  SNAPSHOT_REASON_LABELS,
  type ChartPoint,
  type RiskLevel,
} from "@/lib/health";
import { formatUkDateTime } from "@/lib/recordings";
import type {
  PlacementSession,
  RagThresholds,
  SnapshotPoint,
} from "@/types/health";

const SCORE_MIN = 1;
const SCORE_MAX = 10;

/** The RAG bands behind the line, from the thresholds the API returned. */
function bands(
  thresholds: RagThresholds,
): { level: RiskLevel; from: number; to: number }[] {
  return [
    { level: "green", from: thresholds.green_from, to: SCORE_MAX },
    { level: "amber", from: thresholds.amber_from, to: thresholds.green_from },
    { level: "red", from: SCORE_MIN, to: thresholds.amber_from },
  ];
}

/**
 * The overall score (the Technical score for an SME) after every recompute,
 * on a time axis, with the RAG bands behind it and a vertical line at each
 * completed call. An unscored snapshot leaves a gap. Bands are drawn from
 * the thresholds the API returned, and not at all in the technical view,
 * where the Technical score carries no level.
 */
export function HealthChart({
  history,
  sessions,
  thresholds,
  technical,
}: {
  history: SnapshotPoint[];
  sessions: PlacementSession[];
  thresholds: RagThresholds;
  technical: boolean;
}) {
  const points = chartPoints(history, technical);
  const markers = callMarkers(sessions);
  if (!points.some((p) => p.score !== null)) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="chart-empty">
        No score yet. The chart starts with the first recompute that finds a
        signal.
      </p>
    );
  }
  const seriesLabel = technical ? "Technical" : "Overall";
  const config = {
    score: { label: seriesLabel, color: "var(--chart-1)" },
  } satisfies ChartConfig;
  const domain = chartDomain([...points.map((p) => p.t), ...markers]);

  return (
    <div className="space-y-2">
      <ChartContainer
        config={config}
        className="aspect-auto h-64 w-full"
        data-testid="health-chart"
      >
        <LineChart
          data={points}
          margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
        >
          {/* An array, never a Fragment: Recharts 2 reads its children with a
              react-is that predates React 19, so a Fragment is dropped. */}
          {!technical &&
            bands(thresholds).map((band) => (
              <ReferenceArea
                key={band.level}
                y1={band.from}
                y2={band.to}
                fill={`var(--risk-${band.level})`}
                fillOpacity={0.08}
                ifOverflow="hidden"
              />
            ))}
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain}
            ticks={chartTicks(domain)}
            interval={0}
            tickFormatter={formatUkAxisDate}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[SCORE_MIN, SCORE_MAX]}
            ticks={[1, 3, 5, 7, 9]}
            tickLine={false}
            axisLine={false}
            width={28}
          />
          {markers.map((t) => (
            <ReferenceLine
              key={t}
              x={t}
              stroke="var(--muted-foreground)"
              strokeOpacity={0.5}
              ifOverflow="extendDomain"
            />
          ))}
          <Tooltip
            content={<ScoreTooltip seriesLabel={seriesLabel} />}
            cursor={{ stroke: "var(--border)" }}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="var(--color-score)"
            strokeWidth={2}
            dot={{
              r: 4,
              strokeWidth: 2,
              stroke: "var(--background)",
              fill: "var(--color-score)",
            }}
            activeDot={{ r: 5 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ChartContainer>
      <p className="text-xs text-muted-foreground">
        {seriesLabel} score after every recompute; each vertical line is a call.
        {!technical &&
          ` Green from ${formatScore(thresholds.green_from)}, amber from ${formatScore(thresholds.amber_from)}, red below.`}
      </p>
    </div>
  );
}

/** The snapshot under the pointer: when, the score and its level, and why. */
function ScoreTooltip({
  active,
  payload,
  seriesLabel,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: ChartPoint }>;
  seriesLabel: string;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point || point.score === null) return null;
  return (
    <div className="rounded-lg border border-border/50 bg-background px-2.5 py-1.5 text-xs shadow-xl">
      <p className="font-medium">{formatUkDateTime(point.computed_at)} (UK)</p>
      <p>
        <span className="font-medium tabular-nums">
          {formatScore(point.score)}
        </span>{" "}
        <span className="text-muted-foreground">
          {seriesLabel}
          {point.level
            ? `, ${RISK_LEVEL_LABELS[point.level].toLowerCase()}`
            : ""}
        </span>
      </p>
      <p className="text-muted-foreground">
        {SNAPSHOT_REASON_LABELS[point.reason]}
      </p>
    </div>
  );
}
