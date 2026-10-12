import { Badge } from "@/components/ui/badge";
import { isInFlight, type SessionStatus } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import { cn } from "@/lib/utils";

/**
 * A session's status; a failed one shows its reason on hover. The `dot`
 * form, for dense lists, is a coloured dot and the word: red for failed,
 * the primary colour while in flight, muted once settled.
 */
export function SessionStatusBadge({
  status,
  reason,
  variant = "badge",
}: {
  status: SessionStatus;
  reason?: string | null;
  variant?: "badge" | "dot";
}) {
  if (variant === "dot") {
    const failed = status === "failed";
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 text-sm whitespace-nowrap",
          failed ? "font-medium text-destructive" : "text-muted-foreground",
        )}
        title={failed ? (reason ?? undefined) : undefined}
      >
        <span
          className={cn(
            "size-1.5 rounded-full",
            failed
              ? "bg-destructive"
              : isInFlight(status)
                ? "bg-primary"
                : "bg-muted-foreground",
          )}
          aria-hidden
        />
        {humanize(status)}
      </span>
    );
  }
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
