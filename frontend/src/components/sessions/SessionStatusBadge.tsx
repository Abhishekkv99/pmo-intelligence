import { Badge } from "@/components/ui/badge";
import { isInFlight, type SessionStatus } from "@/lib/recordings";
import { humanize } from "@/lib/register";

/** A session's status; a failed one shows its reason on hover. */
export function SessionStatusBadge({
  status,
  reason,
}: {
  status: SessionStatus;
  reason?: string | null;
}) {
  if (status === "failed") {
    return (
      <Badge variant="destructive" title={reason ?? undefined}>
        Failed
      </Badge>
    );
  }
  return (
    <Badge variant={isInFlight(status) ? "outline" : "secondary"}>
      {humanize(status)}
    </Badge>
  );
}
