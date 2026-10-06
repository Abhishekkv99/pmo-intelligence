"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useProcessingStatus } from "@/hooks/useProcessingStatus";
import type { RunningJob } from "@/types/processing";

export function formatRss(rssMib: number | null): string {
  if (rssMib === null) return "n/a";
  return `${Math.round(rssMib)} MiB`;
}

function shortId(id: string): string {
  return id.split("-")[0];
}

function RunningJobRow({ job }: { job: RunningJob }) {
  const started = new Date(job.started_at).toLocaleTimeString();

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <Badge variant="secondary" className="animate-pulse">
        <span className="mr-1 inline-block h-2 w-2 rounded-full bg-current" />
        {job.kind}
      </Badge>
      <span className="font-mono text-xs text-muted-foreground" title={job.id}>
        {shortId(job.id)}
      </span>
      <span className="text-xs text-muted-foreground">
        started {started} on worker {job.worker}
      </span>
    </li>
  );
}

interface ProcessingStatusPanelProps {
  /** False for anyone without a global role: the route answers 403. */
  enabled: boolean;
}

/**
 * The processing queue and the backend's memory, for the admin page. Every
 * pipeline job (sessions, chat) goes through one queue with a fixed number of
 * slots, so this is the one place that shows what is running and how much is
 * waiting behind it.
 */
export function ProcessingStatusPanel({ enabled }: ProcessingStatusPanelProps) {
  const { status, isBusy, isLoading, error } = useProcessingStatus(enabled);

  if (!enabled) return null;

  return (
    <Card data-testid="processing-status-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-lg">Processing Queue</CardTitle>
            <CardDescription>
              Every pipeline job runs through this queue, one job at a time per
              slot; chat jobs go ahead of session jobs.
            </CardDescription>
          </div>
          {status && (
            <Badge variant={isBusy ? "secondary" : "outline"}>
              {isBusy ? "Busy" : "Idle"}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            Failed to load processing status: {error}
          </div>
        )}

        {isLoading && !status ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : status ? (
          <>
            <dl className="grid gap-3 sm:grid-cols-3">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">
                  Waiting
                </dt>
                <dd
                  className="text-2xl font-semibold"
                  data-testid="queue-depth"
                >
                  {status.queue_depth}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">
                  Running
                </dt>
                <dd
                  className="text-2xl font-semibold"
                  data-testid="queue-running"
                >
                  {status.running.length}
                  <span className="text-base font-normal text-muted-foreground">
                    {" "}
                    of {status.capacity}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">
                  Backend memory
                </dt>
                <dd className="text-2xl font-semibold" data-testid="queue-rss">
                  {formatRss(status.rss_mib)}
                </dd>
              </div>
            </dl>

            {status.running.length > 0 ? (
              <ul className="space-y-2">
                {status.running.map((job) => (
                  <RunningJobRow key={`${job.kind}-${job.id}`} job={job} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nothing is running.
              </p>
            )}

            <p className="text-xs text-muted-foreground">
              {isBusy
                ? "Auto-refreshing every 5 seconds..."
                : "Auto-refreshing every 30 seconds."}
              {status.memory_diagnostics_enabled &&
                " Memory diagnostics are on: the backend logs allocation growth after every job."}
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
