import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { ROUTES } from "@/lib/constants";
import {
  DIMENSION_LABELS,
  SIGNAL_INDICATOR_LABELS,
  formatUkDate,
} from "@/lib/health";
import { formatUkDateTime } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import { SPEAKER_ROLE_LABELS } from "@/lib/sessions";
import type { EvidenceSignal } from "@/types/health";

/**
 * A quote behind a score or a flag: its polarity, dimension, severity,
 * confidence and speaker, when it was said with a link to the call, and,
 * for a score's contributor, the weight the snapshot stored for it.
 */
export function EvidenceItem({
  signal,
  weight,
}: {
  signal: EvidenceSignal;
  weight?: number;
}) {
  const tone =
    signal.polarity === "negative"
      ? "destructive"
      : signal.polarity === "positive"
        ? "secondary"
        : "outline";
  const said = `${formatUkDateTime(signal.occurred_at)} (UK)`;
  return (
    <li className="space-y-1 rounded-md border p-3" data-testid="evidence">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={tone}>{humanize(signal.polarity)}</Badge>
        <span className="font-medium">
          {DIMENSION_LABELS[signal.dimension]}
        </span>
        {signal.indicator && (
          <Badge variant="outline">
            {SIGNAL_INDICATOR_LABELS[signal.indicator]}
          </Badge>
        )}
        <span className="text-muted-foreground">
          severity {signal.severity} · confidence{" "}
          {Math.round(signal.confidence * 100)}%
          {signal.speaker_role
            ? ` · said by ${SPEAKER_ROLE_LABELS[signal.speaker_role]}`
            : ""}
          {weight !== undefined ? ` · weight ${weight.toFixed(2)}` : ""}
        </span>
        {signal.source_kind === "session" ? (
          <Link
            href={`${ROUTES.sessions}/${signal.source_id}`}
            className="text-muted-foreground underline-offset-4 hover:underline"
            title={`Open the call of ${formatUkDate(signal.occurred_at)}`}
          >
            said {said}
          </Link>
        ) : (
          <span className="text-muted-foreground">said {said}</span>
        )}
      </div>
      <blockquote className="border-l-2 pl-3 text-sm italic">
        “{signal.quote}”
      </blockquote>
      {signal.note && (
        <p className="text-sm text-muted-foreground">{signal.note}</p>
      )}
    </li>
  );
}
