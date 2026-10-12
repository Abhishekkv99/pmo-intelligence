import {
  DIMENSION_LABELS,
  formatScore,
  riskLevelFor,
  RISK_LEVEL_LABELS,
  type RiskLevel,
} from "@/lib/health";
import { DIMENSIONS, type Dimension } from "@/lib/sessions";
import { cn } from "@/lib/utils";
import type { RagThresholds, SnapshotDetail } from "@/types/health";

const TILE_CLASSES: Record<RiskLevel, string> = {
  red: "border-risk-red/40 bg-risk-red/5",
  amber: "border-risk-amber/50 bg-risk-amber/5",
  green: "border-risk-green/40 bg-risk-green/5",
};

const DOT_CLASSES: Record<RiskLevel, string> = {
  red: "bg-risk-red",
  amber: "bg-risk-amber",
  green: "bg-risk-green",
};

/**
 * The six dimension scores of the latest snapshot as tiles, each coloured
 * by the thresholds the API returned and naming its level, with how many
 * signals fed it. An SME sees the Technical tile alone, as a plain number.
 * Without a scored snapshot every tile shows a dash.
 */
export function DimensionScores({
  latest,
  thresholds,
  technical,
}: {
  latest: SnapshotDetail | null;
  thresholds: RagThresholds;
  technical: boolean;
}) {
  const dimensions: readonly Dimension[] = technical
    ? ["technical"]
    : DIMENSIONS;
  const counts = new Map(
    (latest?.evidence ?? []).map((e) => [e.dimension, e.signal_count]),
  );
  return (
    <div
      className={cn(
        "grid gap-3",
        technical ? "max-w-xs" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
      )}
      data-testid="dimension-scores"
    >
      {dimensions.map((dimension) => {
        const score = latest?.scored ? latest.scores[dimension] : null;
        const level =
          score !== null && !technical ? riskLevelFor(score, thresholds) : null;
        return (
          <ScoreTile
            key={dimension}
            dimension={dimension}
            score={score}
            level={level}
            count={counts.get(dimension) ?? 0}
          />
        );
      })}
    </div>
  );
}

function ScoreTile({
  dimension,
  score,
  level,
  count,
}: {
  dimension: Dimension;
  score: number | null;
  level: RiskLevel | null;
  count: number;
}) {
  const name = DIMENSION_LABELS[dimension];
  const shown = score === null ? "—" : formatScore(score);
  const signals = `${count} signal${count === 1 ? "" : "s"}`;
  const detail = level ? `${RISK_LEVEL_LABELS[level]} · ${signals}` : signals;
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-3",
        level && TILE_CLASSES[level],
      )}
      data-testid="score-tile"
      aria-label={`${name} ${score === null ? "not scored" : shown}${
        level ? `, ${RISK_LEVEL_LABELS[level].toLowerCase()}` : ""
      }`}
    >
      <p className="text-xs font-medium text-muted-foreground">{name}</p>
      <p className="font-mono text-2xl font-semibold tabular-nums">{shown}</p>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {level && (
          <span
            className={cn("size-2 rounded-full", DOT_CLASSES[level])}
            aria-hidden
          />
        )}
        {detail}
      </p>
    </div>
  );
}
