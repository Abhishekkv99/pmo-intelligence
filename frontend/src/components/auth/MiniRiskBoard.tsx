import { Flag } from "lucide-react";
import {
  HealthBadge,
  TrendIndicator,
} from "@/components/health/HealthIndicators";
import {
  FLAG_SEVERITY_LABELS,
  formatDaysAgo,
  RISK_TRIGGER_LABELS,
} from "@/lib/health";
import { cn } from "@/lib/utils";
import { SAMPLE_FLAG, SAMPLE_ROWS, type SampleFlag } from "./showcase-data";

const UK_TIME_ZONE = "Europe/London";

// Named here, not by Intl: en-GB writes September as "Sept" in some
// runtimes and "Sep" in others, and the page must read the same everywhere.
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** When a quote was said, on a UK clock: "12 Sep · 14:32". */
export function formatSaidAt(iso: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: UK_TIME_ZONE,
      day: "numeric",
      month: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((part) => [part.type, part.value]),
  );
  const month = MONTHS[Number(parts.month) - 1];
  return `${Number(parts.day)} ${month} · ${parts.hour}:${parts.minute}`;
}

const CARD = "rounded-2xl shadow-editorial";

// The sign-in page's product preview: a few rows of the risk board and one
// open flag with its quote, drawn from made-up data with the app's own badges.
export function MiniRiskBoard({ className }: { className?: string }) {
  return (
    <div
      className={cn("flex flex-col gap-4", className)}
      role="group"
      aria-label="Sample risk board and flag"
    >
      <div className={cn(CARD, "overflow-hidden border border-border bg-card")}>
        <div className="flex items-center justify-between border-b border-border bg-muted/60 px-5 py-3.5">
          <span className="font-mono text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
            Placement risk board
          </span>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
            Sample data
          </span>
        </div>
        <ul className="divide-y divide-border">
          {SAMPLE_ROWS.map((row) => (
            <li
              key={row.placement_id}
              className="flex items-center justify-between gap-3 px-5 py-4"
              data-testid="sample-row"
            >
              <div className="min-w-0">
                <div className="text-[15px] font-bold text-foreground sm:truncate">
                  {row.consultant.name} · {row.client.name}
                </div>
                {row.days_since_last_call !== null && (
                  <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                    Last call {formatDaysAgo(row.days_since_last_call)}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2.5 font-mono text-xs font-semibold">
                <TrendIndicator trend={row.trend} delta={row.trend_delta} />
                <HealthBadge
                  score={row.overall}
                  level={row.risk_level}
                  className="font-mono text-sm"
                />
              </div>
            </li>
          ))}
        </ul>
      </div>
      <SampleFlagCard flag={SAMPLE_FLAG} />
    </div>
  );
}

function SampleFlagCard({ flag }: { flag: SampleFlag }) {
  return (
    <div
      className={cn(
        CARD,
        "border-2 border-risk-red/25 bg-[color-mix(in_oklch,var(--risk-red)_5%,var(--card))] p-6",
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-md bg-risk-red/10 p-1 text-risk-red">
          <Flag className="size-4" aria-hidden />
        </span>
        <span className="font-mono text-xs font-bold tracking-wider text-risk-red uppercase">
          {RISK_TRIGGER_LABELS[flag.trigger]}
        </span>
        <span className="ml-auto rounded-full bg-risk-red px-2 py-0.5 text-xs font-medium text-risk-red-foreground">
          {FLAG_SEVERITY_LABELS[flag.severity]}
        </span>
      </div>
      <blockquote className="my-2 border-l-2 border-risk-red pl-3.5 text-base leading-snug font-medium text-foreground">
        “{flag.quote}”
      </blockquote>
      <div className="mt-3.5 border-t border-risk-red/20 pt-3 font-mono text-xs text-muted-foreground">
        Said on a call, {formatSaidAt(flag.occurred_at)}
      </div>
    </div>
  );
}
