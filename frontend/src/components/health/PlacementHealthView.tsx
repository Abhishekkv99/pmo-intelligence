"use client";

import Link from "next/link";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { DimensionScores } from "@/components/health/DimensionScores";
import { EvidenceItem } from "@/components/health/EvidenceItem";
import { FlagList } from "@/components/health/FlagList";
import { HealthChart } from "@/components/health/HealthChart";
import {
  HealthBadge,
  NotScored,
  TrendIndicator,
} from "@/components/health/HealthIndicators";
import { SessionStatusBadge } from "@/components/sessions/SessionStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePlacementHealth } from "@/hooks/useHealth";
import { ApiError } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import {
  DIMENSION_LABELS,
  formatDate,
  formatScore,
  formatUkDate,
  formatWeeksIn,
  isOverdue,
  placementPath,
  SNAPSHOT_REASON_LABELS,
  ukToday,
} from "@/lib/health";
import { formatUkDateTime } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import {
  formatDuration,
  SESSION_KIND_LABELS,
  SPEAKER_ROLE_LABELS,
} from "@/lib/sessions";
import { cn } from "@/lib/utils";
import type {
  DimensionEvidence,
  OpenIssue,
  OtherPlacement,
  PersonView,
  PlacementAction,
  PlacementHealth,
  PlacementSession,
  RegisterFields,
  SnapshotDetail,
} from "@/types/health";

/**
 * The placement (consultant) page: who and where, the overall and the six
 * dimension scores with the quotes that moved them, the health chart over
 * the placement's life with its calls marked, the open flags with their
 * evidence, the calls, the open issues, every action and the consultant's
 * other placements. An SME sees the technical view: the Technical score and
 * trend, its evidence and the register's dates and people, nothing else of
 * the health. A placement outside the reader's scope shows "not found".
 */
export function PlacementHealthView({ placementId }: { placementId: string }) {
  const { health, isLoading, error } = usePlacementHealth(placementId);

  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        title="Placement not found"
        description="It does not exist, or it is not one of your placements."
        action={{ label: "Risk board", href: ROUTES.home }}
      />
    );
  }
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error instanceof Error
          ? error.message
          : "Could not load the placement"}
      </p>
    );
  }
  if (isLoading || !health) return <LoadingSpinner />;

  const technical = health.view === "technical";
  const latest = health.latest;
  const today = ukToday();

  return (
    <div className="space-y-6">
      <div className="text-sm">
        <Link
          href={ROUTES.home}
          className="text-muted-foreground hover:underline"
        >
          ← Risk board
        </Link>
      </div>
      <Header health={health} technical={technical} />

      <DimensionScores
        latest={latest}
        thresholds={health.thresholds}
        technical={technical}
      />

      <Section title="Health over the placement">
        <HealthChart
          history={health.history}
          sessions={health.sessions}
          thresholds={health.thresholds}
          technical={technical}
        />
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        {!technical && (
          <Section title="Open flags" count={health.open_flags.length}>
            <FlagList flags={health.open_flags} />
          </Section>
        )}
        <Section title="What moved the scores">
          <Contributors evidence={latest?.scored ? latest.evidence : []} />
        </Section>
      </div>

      {/* The calls table's six columns need the full width. */}
      <Section title="Calls" count={health.sessions.length}>
        <CallsTable sessions={health.sessions} />
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Open issues" count={health.open_issues.length}>
          <IssueList issues={health.open_issues} />
        </Section>
        <Section title="Actions" count={health.actions.length}>
          <ActionList actions={health.actions} today={today} />
        </Section>
      </div>

      {health.other_placements.length > 0 && (
        <Section
          title="Other placements"
          count={health.other_placements.length}
        >
          <OtherPlacements placements={health.other_placements} />
        </Section>
      )}
    </div>
  );
}

function Header({
  health,
  technical,
}: {
  health: PlacementHealth;
  technical: boolean;
}) {
  const latest = health.latest;
  const scored = latest?.scored ?? false;
  const status = health.register_fields.status;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold tracking-tight">
          {health.consultant.name}
        </h2>
        {technical ? (
          <TechnicalScore latest={latest} />
        ) : (
          <HealthBadge
            score={scored ? latest!.overall : null}
            level={scored ? latest!.risk_level : null}
            className="text-sm"
          />
        )}
        {latest && scored && (
          <TrendIndicator
            trend={technical ? latest.technical_trend : latest.trend}
            delta={
              technical ? latest.technical_trend_delta : latest.trend_delta
            }
          />
        )}
        <Badge variant={status === "active" ? "secondary" : "outline"}>
          {humanize(status)}
        </Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        {health.client.name} · {health.project.name} ·{" "}
        {formatWeeksIn(health.weeks_in)}
      </p>
      <RegisterLine fields={health.register_fields} />
      {latest && (
        <p className="text-xs text-muted-foreground" data-testid="computed-at">
          {scored ? "Scored" : "Not scored"}{" "}
          {formatUkDateTime(latest.computed_at)} (UK),{" "}
          {SNAPSHOT_REASON_LABELS[latest.reason].toLowerCase()}
          {latest.signal_count !== null
            ? `, from ${latest.signal_count} signal${latest.signal_count === 1 ? "" : "s"}`
            : ""}
          {scored ? "" : ": no signal in the scoring window"}
        </p>
      )}
    </div>
  );
}

/** An SME's Technical score: a plain number, since it carries no level. */
function TechnicalScore({ latest }: { latest: SnapshotDetail | null }) {
  const score = latest?.scored ? latest.scores.technical : null;
  if (score === null) return <NotScored />;
  return (
    <span className="text-xl font-semibold" data-testid="technical-score">
      {formatScore(score)}{" "}
      <span className="text-sm font-normal text-muted-foreground">
        Technical
      </span>
    </span>
  );
}

function personName(person: PersonView | null): string {
  return person ? (person.full_name ?? person.email) : "—";
}

/** The register's fields in one line; an SME is not given the contract ones. */
function RegisterLine({ fields }: { fields: RegisterFields }) {
  const items: [string, string][] = [
    ["Started", formatDate(fields.start_date)],
    [
      "Expected end",
      fields.expected_end_date
        ? formatDate(fields.expected_end_date)
        : "open-ended",
    ],
  ];
  if (fields.stack) items.push(["Stack", fields.stack]);
  if (fields.extension_status) {
    items.push(["Extension", humanize(fields.extension_status).toLowerCase()]);
  }
  if (fields.rate_band) items.push(["Rate band", fields.rate_band]);
  if (fields.ended_reason) items.push(["Ended", fields.ended_reason]);
  items.push(
    ["PS", personName(fields.ps)],
    ["SME", personName(fields.sme)],
    ["Tech lead", personName(fields.tech_lead)],
    ["Client manager", fields.client_manager_name ?? "—"],
  );
  return (
    <dl
      className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
      data-testid="register-fields"
    >
      {items.map(([label, value]) => (
        <div key={label} className="flex gap-1">
          <dt className="text-muted-foreground">{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Per dimension, the signals that pulled its score furthest from the prior. */
function Contributors({ evidence }: { evidence: DimensionEvidence[] }) {
  const shown = evidence.filter((e) => e.contributors.length > 0);
  if (shown.length === 0) {
    return <Nothing>No signal in the scoring window.</Nothing>;
  }
  return (
    <div className="space-y-4">
      {shown.map((e) => (
        <div key={e.dimension} className="space-y-2" data-testid="contributors">
          <p className="text-sm font-medium">
            {DIMENSION_LABELS[e.dimension]}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {e.signal_count} signal{e.signal_count === 1 ? "" : "s"}
            </span>
          </p>
          <ul className="space-y-2">
            {e.contributors.map((c) => (
              <EvidenceItem
                key={c.signal.id}
                signal={c.signal}
                weight={c.weight}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function CallsTable({ sessions }: { sessions: PlacementSession[] }) {
  if (sessions.length === 0) return <Nothing>No calls yet.</Nothing>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Call (UK time)</TableHead>
          <TableHead>Kind</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Length</TableHead>
          <TableHead>Signals</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sessions.map((s) => (
          <TableRow key={s.id} data-testid="call">
            <TableCell>
              <Link
                href={`${ROUTES.sessions}/${s.id}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {formatUkDateTime(s.held_at)}
              </Link>
            </TableCell>
            <TableCell>
              {s.kind ? (
                SESSION_KIND_LABELS[s.kind]
              ) : (
                <span className="text-muted-foreground">Not classified</span>
              )}
            </TableCell>
            <TableCell>
              <SessionStatusBadge status={s.status} />
            </TableCell>
            <TableCell>{formatDuration(s.duration_seconds)}</TableCell>
            <TableCell className="tabular-nums">{s.signal_count}</TableCell>
            <TableCell className="tabular-nums">{s.action_count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function IssueList({ issues }: { issues: OpenIssue[] }) {
  if (issues.length === 0) return <Nothing>No open issues.</Nothing>;
  return (
    <ul className="space-y-2">
      {issues.map((issue) => (
        <li
          key={issue.id}
          className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm"
          data-testid="issue"
        >
          <span className="font-medium">{issue.topic}</span>
          <Badge variant="outline">{humanize(issue.status)}</Badge>
          <span className="text-xs text-muted-foreground">
            seen in {issue.occurrence_count} call
            {issue.occurrence_count === 1 ? "" : "s"} since{" "}
            {formatUkDate(issue.first_seen_at)}, last{" "}
            {formatUkDate(issue.last_seen_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Every action in the server's order: open and overdue by due date, then
 * done ones, newest closed first, in muted text with their closed date.
 */
function ActionList({
  actions,
  today,
}: {
  actions: PlacementAction[];
  today: string;
}) {
  if (actions.length === 0) return <Nothing>No actions.</Nothing>;
  return (
    <ul className="space-y-2">
      {actions.map((action) => {
        const done = action.status === "done";
        const overdue =
          !done &&
          action.due_date !== null &&
          isOverdue(action.due_date, today);
        const owner =
          action.owner?.full_name ??
          action.owner?.email ??
          SPEAKER_ROLE_LABELS[action.owner_role];
        return (
          <li
            key={action.id}
            className={cn(
              "space-y-1 rounded-md border p-3",
              done && "text-muted-foreground",
            )}
            data-testid="action"
            data-done={done}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{action.description}</span>
              {done ? (
                <Badge variant="secondary">Done</Badge>
              ) : overdue ? (
                <Badge className="bg-risk-red text-risk-red-foreground">
                  Overdue
                </Badge>
              ) : (
                <Badge variant="outline">{humanize(action.status)}</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Owner: {owner}
              {action.due_date
                ? ` · due ${formatDate(action.due_date)}`
                : action.due_text
                  ? ` · due ${action.due_text}`
                  : ""}
              {done && action.closed_at
                ? ` · done ${formatUkDate(action.closed_at)}`
                : ""}
              {action.source_kind === "session" && (
                <>
                  {" · "}
                  <Link
                    href={`${ROUTES.sessions}/${action.source_id}`}
                    className="underline-offset-4 hover:underline"
                  >
                    agreed on a call
                  </Link>
                </>
              )}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function OtherPlacements({ placements }: { placements: OtherPlacement[] }) {
  return (
    <ul className="space-y-1 text-sm">
      {placements.map((p) => (
        <li key={p.id} data-testid="other-placement">
          <Link
            href={placementPath(p.id)}
            className="font-medium underline-offset-4 hover:underline"
          >
            {p.client.name} · {p.project.name}
          </Link>{" "}
          <span className="text-muted-foreground">
            {formatDate(p.start_date)} to{" "}
            {p.expected_end_date
              ? formatDate(p.expected_end_date)
              : "open-ended"}{" "}
            · {humanize(p.status).toLowerCase()}
          </span>
        </li>
      ))}
    </ul>
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
