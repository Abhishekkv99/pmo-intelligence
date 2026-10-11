"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/common/DataTable";
import {
  HealthBadge,
  LEVEL_CLASSES,
  NotScored,
  TrendIndicator,
} from "@/components/health/HealthIndicators";
import { useAuth } from "@/components/providers/AuthProvider";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRiskBoard } from "@/hooks/useHealth";
import {
  formatDate,
  formatDaysAgo,
  formatScore,
  formatUkDate,
  FLAG_SEVERITY_LABELS,
  isOverdue,
  placementPath,
  RISK_LEVEL_LABELS,
  RISK_LEVELS,
  RISK_TRIGGER_LABELS,
  ukToday,
} from "@/lib/health";
import { cn } from "@/lib/utils";
import type { FlagSummary, NextAction, RiskBoardRow } from "@/types/health";

const ALL = "all";
const NOT_SCORED = "not_scored";

/**
 * The risk board: every active placement the user may read, in the server's
 * order (red first, then falling, then lowest overall; not scored last).
 * An SME sees the technical view: the Technical score and its trend, no
 * flags and no risk filter, in the order of their Technical scores. The
 * consultant's name opens the placement page.
 */
export function RiskBoard() {
  const { user } = useAuth();
  const { rows, isLoading, error } = useRiskBoard();
  const technical =
    user?.role === "sme" || (rows ?? []).some((r) => r.view === "technical");
  const [ps, setPs] = useState(ALL);
  const [cdm, setCdm] = useState(ALL);
  const [client, setClient] = useState(ALL);
  const [stack, setStack] = useState(ALL);
  const [level, setLevel] = useState(ALL);

  const options = useMemo(() => filterOptions(rows ?? []), [rows]);
  const today = ukToday();

  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (r) =>
          (ps === ALL || r.ps?.id === ps) &&
          (cdm === ALL || r.cdm?.id === cdm) &&
          (client === ALL || r.client.id === client) &&
          (stack === ALL || r.stack === stack) &&
          (technical || level === ALL || levelKey(r) === level),
      ),
    [rows, ps, cdm, client, stack, level, technical],
  );

  const columns = useMemo<ColumnDef<RiskBoardRow>[]>(() => {
    const scoreColumns: ColumnDef<RiskBoardRow>[] = technical
      ? [
          {
            id: "technical",
            header: "Technical",
            accessorFn: (r) => (r.technical === null ? "" : r.technical),
            cell: ({ row }) =>
              row.original.technical === null ? (
                <NotScored />
              ) : (
                <span className="font-medium tabular-nums">
                  {formatScore(row.original.technical)}
                </span>
              ),
          },
          {
            id: "trend",
            header: "Trend",
            accessorFn: (r) => r.technical_trend ?? "",
            cell: ({ row }) => (
              <TrendIndicator
                trend={row.original.technical_trend}
                delta={row.original.technical_trend_delta}
              />
            ),
          },
        ]
      : [
          {
            id: "health",
            header: "Health",
            accessorFn: (r) =>
              r.risk_level ? RISK_LEVEL_LABELS[r.risk_level] : "Not scored",
            cell: ({ row }) => (
              <HealthBadge
                score={row.original.overall}
                level={row.original.risk_level}
              />
            ),
          },
          {
            id: "trend",
            header: "Trend",
            accessorFn: (r) => r.trend ?? "",
            cell: ({ row }) => (
              <TrendIndicator
                trend={row.original.trend}
                delta={row.original.trend_delta}
              />
            ),
          },
          {
            id: "flags",
            header: "Flags",
            accessorFn: (r) =>
              r.open_flags.map((f) => RISK_TRIGGER_LABELS[f.trigger]).join(" "),
            cell: ({ row }) => <FlagChips flags={row.original.open_flags} />,
          },
        ];
    return [
      {
        id: "consultant",
        header: "Consultant",
        accessorFn: (r) => r.consultant.name,
        cell: ({ row }) => (
          <Link
            href={placementPath(row.original.placement_id)}
            className="font-medium underline-offset-4 hover:underline"
          >
            {row.original.consultant.name}
          </Link>
        ),
      },
      {
        id: "placement",
        header: "Client · project",
        accessorFn: (r) => `${r.client.name} · ${r.project.name}`,
      },
      {
        id: "weeks",
        header: "Weeks in",
        accessorFn: (r) => r.weeks_in,
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.weeks_in}</span>
        ),
      },
      ...scoreColumns,
      {
        id: "last_call",
        header: "Last call",
        accessorFn: (r) =>
          r.days_since_last_call === null
            ? ""
            : formatDaysAgo(r.days_since_last_call),
        cell: ({ row }) =>
          row.original.days_since_last_call === null ? (
            <span className="text-muted-foreground">No call yet</span>
          ) : (
            formatDaysAgo(row.original.days_since_last_call)
          ),
      },
      {
        id: "next_action",
        header: "Next action",
        accessorFn: (r) => r.next_action?.description ?? "",
        cell: ({ row }) => (
          <NextActionCell action={row.original.next_action} today={today} />
        ),
      },
    ];
  }, [technical, today]);

  return (
    <div className="space-y-4">
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <DataTable
        columns={columns}
        data={shown}
        isLoading={isLoading}
        sortable={false}
        searchPlaceholder="Search placements"
        emptyMessage="No active placements yet. Each one appears here with its health once it is in the register."
        toolbar={
          <>
            <PeopleFilter
              label="Placement specialist filter"
              all="All placement specialists"
              value={ps}
              onChange={setPs}
              options={options.ps}
            />
            <PeopleFilter
              label="CDM filter"
              all="All CDMs"
              value={cdm}
              onChange={setCdm}
              options={options.cdms}
            />
            <PeopleFilter
              label="Client filter"
              all="All clients"
              value={client}
              onChange={setClient}
              options={options.clients}
            />
            <PeopleFilter
              label="Stack filter"
              all="All stacks"
              value={stack}
              onChange={setStack}
              options={options.stacks}
            />
            {!technical && (
              <Select value={level} onValueChange={setLevel}>
                <SelectTrigger className="w-40" aria-label="Risk level filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All levels</SelectItem>
                  {RISK_LEVELS.map((l) => (
                    <SelectItem key={l} value={l}>
                      {RISK_LEVEL_LABELS[l]}
                    </SelectItem>
                  ))}
                  <SelectItem value={NOT_SCORED}>Not scored</SelectItem>
                </SelectContent>
              </Select>
            )}
          </>
        }
      />
    </div>
  );
}

function levelKey(row: RiskBoardRow): string {
  return row.risk_level ?? NOT_SCORED;
}

type Option = [id: string, name: string];

function filterOptions(rows: RiskBoardRow[]) {
  const ps = new Map<string, string>();
  const cdms = new Map<string, string>();
  const clients = new Map<string, string>();
  const stacks = new Map<string, string>();
  for (const r of rows) {
    if (r.ps) ps.set(r.ps.id, r.ps.full_name ?? r.ps.email);
    if (r.cdm) cdms.set(r.cdm.id, r.cdm.full_name ?? r.cdm.email);
    clients.set(r.client.id, r.client.name);
    if (r.stack) stacks.set(r.stack, r.stack);
  }
  const sorted = (m: Map<string, string>): Option[] =>
    [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  return {
    ps: sorted(ps),
    cdms: sorted(cdms),
    clients: sorted(clients),
    stacks: sorted(stacks),
  };
}

function PeopleFilter({
  label,
  all,
  value,
  onChange,
  options,
}: {
  label: string;
  all: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-52" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{all}</SelectItem>
        {options.map(([id, name]) => (
          <SelectItem key={id} value={id}>
            {name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function FlagChips({ flags }: { flags: FlagSummary[] }) {
  if (flags.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {flags.map((flag) => (
        <Badge
          key={flag.id}
          variant={flag.severity === "critical" ? "default" : "outline"}
          className={cn(flag.severity === "critical" && LEVEL_CLASSES.red)}
          title={`${FLAG_SEVERITY_LABELS[flag.severity]}, opened ${formatUkDate(flag.opened_at)}`}
          data-testid="flag"
        >
          {RISK_TRIGGER_LABELS[flag.trigger]}
        </Badge>
      ))}
    </div>
  );
}

function NextActionCell({
  action,
  today,
}: {
  action: NextAction | null;
  today: string;
}) {
  if (action === null) return <span className="text-muted-foreground">—</span>;
  const overdue = isOverdue(action.due_date, today);
  return (
    <div className="max-w-xs">
      <span
        className={cn(
          "text-sm tabular-nums",
          overdue ? "font-medium text-risk-red" : "text-muted-foreground",
        )}
      >
        {formatDate(action.due_date)}
        {overdue && " · overdue"}
      </span>
      <p className="truncate" title={action.description}>
        {action.description}
      </p>
    </div>
  );
}
