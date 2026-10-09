"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Play, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  AudioPlayer,
  type AudioPlayerHandle,
} from "@/components/sessions/AudioPlayer";
import { SessionStatusBadge } from "@/components/sessions/SessionStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { retrySession, setSessionKind, useSession } from "@/hooks/useSessions";
import { ApiError } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { formatUkDateTime, formatUsd, isInFlight } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import { hasGlobalRole } from "@/lib/roles";
import {
  formatDuration,
  formatOffset,
  SESSION_KIND_LABELS,
  SESSION_KINDS,
  SPEAKER_ROLE_LABELS,
  speakerLabel,
  type SessionKind,
} from "@/lib/sessions";
import type { ActionView, SessionDetail, SignalView } from "@/types/sessions";

type Seek = ((ms: number) => void) | null;

/** A button that plays the recording from `ms`; plain text without a player. */
function SeekButton({ ms, seek }: { ms: number | null; seek: Seek }) {
  if (ms === null) return null;
  if (!seek) {
    return (
      <span className="text-xs text-muted-foreground tabular-nums">
        {formatOffset(ms)}
      </span>
    );
  }
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-6 gap-1 px-1.5 text-xs tabular-nums"
      aria-label={`Play from ${formatOffset(ms)}`}
      onClick={() => seek(ms)}
    >
      <Play className="size-3" />
      {formatOffset(ms)}
    </Button>
  );
}

function Header({
  session,
  isGlobal,
  onChanged,
}: {
  session: SessionDetail;
  isGlobal: boolean;
  onChanged: (next?: SessionDetail) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function changeKind(kind: string) {
    setBusy(true);
    try {
      onChanged(await setSessionKind(session.id, kind as SessionKind));
      toast.success("Kind of call saved");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    setBusy(true);
    try {
      await retrySession(session.id);
      toast.success("Queued again");
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not retry");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold tracking-tight">
          {session.consultant.name}
        </h2>
        <SessionStatusBadge
          status={session.status}
          reason={session.error_message}
        />
        {isGlobal && session.status === "failed" && (
          <Button size="sm" variant="outline" disabled={busy} onClick={retry}>
            <RotateCcw className="size-4" />
            Retry
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        {session.client.name} · {session.project.name} ·{" "}
        {formatUkDateTime(session.held_at)} (UK) ·{" "}
        {formatDuration(session.duration_seconds)}
        {session.project_phase ? ` · ${session.project_phase}` : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Kind of call:</span>
        {isGlobal ? (
          <Select
            value={session.kind ?? undefined}
            onValueChange={changeKind}
            disabled={busy}
          >
            <SelectTrigger className="h-8 w-44" aria-label="Kind of call">
              <SelectValue placeholder="Not classified" />
            </SelectTrigger>
            <SelectContent>
              {SESSION_KINDS.map((kind) => (
                <SelectItem key={kind} value={kind}>
                  {SESSION_KIND_LABELS[kind]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span>
            {session.kind
              ? SESSION_KIND_LABELS[session.kind]
              : "Not classified"}
          </span>
        )}
        {session.kind_overridden && (
          <span className="text-xs text-muted-foreground">
            set by a person
            {session.session_class
              ? `; classified as ${SESSION_KIND_LABELS[session.session_class]}`
              : ""}
          </span>
        )}
      </div>
      {session.status === "failed" && session.error_message && (
        <p
          role="alert"
          className="text-sm text-destructive"
          data-testid="session-error"
        >
          {session.error_message}
        </p>
      )}
    </div>
  );
}

function SignalItem({ signal, seek }: { signal: SignalView; seek: Seek }) {
  const tone =
    signal.polarity === "negative"
      ? "destructive"
      : signal.polarity === "positive"
        ? "secondary"
        : "outline";
  return (
    <li className="space-y-1 rounded-md border p-3" data-testid="signal">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={tone}>{humanize(signal.polarity)}</Badge>
        <span className="font-medium">{humanize(signal.dimension)}</span>
        <span className="text-muted-foreground">
          severity {signal.severity} · confidence{" "}
          {Math.round(signal.confidence * 100)}%
          {signal.speaker_role
            ? ` · said by ${SPEAKER_ROLE_LABELS[signal.speaker_role]}`
            : ""}
        </span>
        <SeekButton ms={signal.offset_ms} seek={seek} />
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

function ActionItem({ action, seek }: { action: ActionView; seek: Seek }) {
  const owner =
    action.owner?.full_name ??
    action.owner?.email ??
    SPEAKER_ROLE_LABELS[action.owner_role];
  return (
    <li className="space-y-1 rounded-md border p-3" data-testid="action">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{action.description}</span>
        <Badge variant={action.status === "done" ? "secondary" : "outline"}>
          {humanize(action.status)}
        </Badge>
        <SeekButton ms={action.offset_ms} seek={seek} />
      </div>
      <p className="text-xs text-muted-foreground">
        Owner: {owner}
        {action.due_text || action.due_date
          ? ` · due ${action.due_text ?? ""}${
              action.due_date ? ` (${action.due_date})` : ""
            }`
          : ""}
      </p>
      <blockquote className="border-l-2 pl-3 text-sm italic">
        “{action.quote}”
      </blockquote>
    </li>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {title}
          {count !== undefined && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {count}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Nothing({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

/**
 * One recorded call: who and when, the recording, the summary, the
 * transcript by speaker, and what the analysis read from it, each with the
 * words it came from and a button to play the recording from there. PMO
 * managers and admins also correct the kind of call, retry a failed session
 * and see the analysis steps that failed.
 */
export function SessionView({ sessionId }: { sessionId: string }) {
  const { user } = useAuth();
  const isGlobal = hasGlobalRole(user?.role);
  const { session, isLoading, error, mutate } = useSession(sessionId);
  const player = useRef<AudioPlayerHandle>(null);

  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        title="Session not found"
        description="It does not exist, or it is not one of your placements."
        action={{ label: "All sessions", href: ROUTES.sessions }}
      />
    );
  }
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error instanceof Error ? error.message : "Could not load the session"}
      </p>
    );
  }
  if (isLoading || !session) return <LoadingSpinner />;

  const seek: Seek = session.has_recording
    ? (ms) => player.current?.seek(ms)
    : null;
  const analysed = session.status === "completed";

  return (
    <div className="space-y-6">
      <div className="text-sm">
        <Link
          href={ROUTES.sessions}
          className="text-muted-foreground hover:underline"
        >
          ← Sessions
        </Link>
      </div>
      <Header
        session={session}
        isGlobal={isGlobal}
        onChanged={(next) =>
          void (next ? mutate(next, { revalidate: false }) : mutate())
        }
      />

      {isInFlight(session.status) && (
        <p className="text-sm text-muted-foreground" data-testid="in-flight">
          This call is being processed; the page updates by itself.
        </p>
      )}

      {session.has_recording && (
        <AudioPlayer ref={player} sessionId={session.id} />
      )}

      <Section title="Summary">
        {session.summary ? (
          <p className="text-sm leading-relaxed">{session.summary}</p>
        ) : (
          <Nothing>
            {analysed ? "No summary was produced." : "Not analysed yet."}
          </Nothing>
        )}
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Signals" count={session.signals.length}>
          {session.signals.length ? (
            <ul className="space-y-2">
              {session.signals.map((s) => (
                <SignalItem key={s.id} signal={s} seek={seek} />
              ))}
            </ul>
          ) : (
            <Nothing>No signals.</Nothing>
          )}
          {session.quotes_rejected > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              {session.quotes_rejected} item(s) dropped because their quote was
              not found in the transcript.
            </p>
          )}
        </Section>

        <div className="space-y-6">
          <Section title="Issues" count={session.issues.length}>
            {session.issues.length ? (
              <ul className="space-y-2">
                {session.issues.map((issue) => (
                  <li
                    key={issue.id}
                    className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm"
                    data-testid="issue"
                  >
                    <span className="font-medium">{issue.topic}</span>
                    <Badge
                      variant={
                        issue.status === "open" ? "outline" : "secondary"
                      }
                    >
                      {humanize(issue.status)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      seen in {issue.occurrence_count} call
                      {issue.occurrence_count === 1 ? "" : "s"} since{" "}
                      {formatUkDateTime(issue.first_seen_at)}
                    </span>
                    <SeekButton ms={issue.offset_ms} seek={seek} />
                  </li>
                ))}
              </ul>
            ) : (
              <Nothing>No issues.</Nothing>
            )}
          </Section>

          <Section title="Actions agreed" count={session.actions.length}>
            {session.actions.length ? (
              <ul className="space-y-2">
                {session.actions.map((a) => (
                  <ActionItem key={a.id} action={a} seek={seek} />
                ))}
              </ul>
            ) : (
              <Nothing>No actions.</Nothing>
            )}
            {session.closed_actions.length > 0 && (
              <div className="mt-4 space-y-1">
                <p className="text-sm font-medium">
                  Earlier actions this call closed
                </p>
                <ul className="list-disc pl-5 text-sm">
                  {session.closed_actions.map((a) => (
                    <li key={a.id}>{a.description}</li>
                  ))}
                </ul>
              </div>
            )}
          </Section>

          <Section title="Cost">
            <p className="text-sm" data-testid="session-cost">
              {formatUsd(session.cost.total_usd)}{" "}
              <span className="text-muted-foreground">
                (transcription {formatUsd(session.cost.transcription_usd)},
                analysis {formatUsd(session.cost.analysis_usd)})
              </span>
            </p>
          </Section>
        </div>
      </div>

      <Section title="Transcript" count={session.utterances.length}>
        {session.utterances.length ? (
          <ol className="space-y-2">
            {session.utterances.map((u, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <div className="w-44 shrink-0">
                  <div className="font-medium">
                    {speakerLabel(u.speaker, session.speakers)}
                  </div>
                  <SeekButton ms={u.start_ms} seek={seek} />
                </div>
                <p className="leading-relaxed">{u.text}</p>
              </li>
            ))}
          </ol>
        ) : (
          <Nothing>No transcript yet.</Nothing>
        )}
      </Section>

      {session.node_errors && session.node_errors.length > 0 && (
        <Section
          title="Analysis steps that failed"
          count={session.node_errors.length}
        >
          <ul className="space-y-1 text-sm" data-testid="node-errors">
            {session.node_errors.map((e, i) => (
              <li key={i}>
                <span className="font-medium">{humanize(e.node)}</span>:{" "}
                {e.error}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
