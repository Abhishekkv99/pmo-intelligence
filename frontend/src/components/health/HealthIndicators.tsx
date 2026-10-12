import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  formatDelta,
  formatScore,
  RISK_LEVEL_LABELS,
  TREND_LABELS,
  type RiskLevel,
  type Trend,
} from "@/lib/health";
import { cn } from "@/lib/utils";

/** A RAG level's colours (theme tokens, light and dark). */
export const LEVEL_CLASSES: Record<RiskLevel, string> = {
  red: "bg-risk-red text-risk-red-foreground",
  amber: "bg-risk-amber text-risk-amber-foreground",
  green: "bg-risk-green text-risk-green-foreground",
};

export function NotScored() {
  return <span className="text-muted-foreground">Not scored</span>;
}

/** A score in its level's colour with the level word; "Not scored" without one. */
export function HealthBadge({
  score,
  level,
  className,
}: {
  score: number | null;
  level: RiskLevel | null;
  className?: string;
}) {
  if (level === null || score === null) return <NotScored />;
  return (
    <Badge
      className={cn("gap-1.5 tabular-nums", LEVEL_CLASSES[level], className)}
      data-testid="health-badge"
    >
      <span className="font-mono">{formatScore(score)}</span>
      <span>{RISK_LEVEL_LABELS[level]}</span>
    </Badge>
  );
}

const TREND_ICONS: Record<Trend, typeof ArrowUp> = {
  up: ArrowUp,
  flat: ArrowRight,
  down: ArrowDown,
};

/** A trend's arrow and its change over 14 days; a dash before there is one. */
export function TrendIndicator({
  trend,
  delta,
}: {
  trend: Trend | null;
  delta: number | null;
}) {
  if (trend === null) {
    return (
      <span className="text-muted-foreground" title="No score 14 days back yet">
        —
      </span>
    );
  }
  const Icon = TREND_ICONS[trend];
  const label =
    delta === null
      ? TREND_LABELS[trend]
      : `${TREND_LABELS[trend]}, ${formatDelta(delta)} over 14 days`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 tabular-nums",
        trend === "down" && "text-risk-red",
        trend === "up" && "text-risk-green",
      )}
      title={label}
      aria-label={label}
    >
      <Icon className="h-4 w-4" aria-hidden />
      {delta !== null && formatDelta(delta)}
    </span>
  );
}
