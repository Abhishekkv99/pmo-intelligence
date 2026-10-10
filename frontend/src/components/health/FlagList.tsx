import { EvidenceItem } from "@/components/health/EvidenceItem";
import { LEVEL_CLASSES } from "@/components/health/HealthIndicators";
import { Badge } from "@/components/ui/badge";
import {
  FLAG_SEVERITY_LABELS,
  formatUkDate,
  RISK_TRIGGER_LABELS,
} from "@/lib/health";
import { cn } from "@/lib/utils";
import type { FlagDetail } from "@/types/health";

/**
 * The open flags in the server's order (critical first, then the oldest),
 * each with its severity, when it opened and the quotes behind it. A flag
 * raised from the register (contract horizon) has no quote.
 */
export function FlagList({ flags }: { flags: FlagDetail[] }) {
  if (flags.length === 0) {
    return <p className="text-sm text-muted-foreground">No open flags.</p>;
  }
  return (
    <ul className="space-y-3">
      {flags.map((flag) => (
        <li
          key={flag.id}
          className="space-y-2 rounded-md border p-3"
          data-testid="flag"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {RISK_TRIGGER_LABELS[flag.trigger]}
            </span>
            <Badge
              variant={flag.severity === "critical" ? "default" : "outline"}
              className={cn(flag.severity === "critical" && LEVEL_CLASSES.red)}
            >
              {FLAG_SEVERITY_LABELS[flag.severity]}
            </Badge>
            <span className="text-xs text-muted-foreground">
              opened {formatUkDate(flag.opened_at)}
            </span>
          </div>
          {flag.evidence.length > 0 ? (
            <ul className="space-y-2">
              {flag.evidence.map((signal) => (
                <EvidenceItem key={signal.id} signal={signal} />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">
              Raised from the placement&apos;s register, not from a quote.
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
