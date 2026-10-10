"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";
import { DataTable } from "@/components/common/DataTable";
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
  formatDelta,
  formatScore,
  FLAG_SEVERITY_LABELS,
  isOverdue,
  RISK_LEVEL_LABELS,
  RISK_LEVELS,
  RISK_TRIGGER_LABELS,
  TREND_LABELS,
  ukToday,
  type RiskLevel,
  type Trend,
} from "@/lib/health";
import { cn } from "@/lib/utils";
import type { FlagSummary, NextAction, RiskBoardRow } from "@/types/health";

const ALL = "all";
const NOT_SCORED = "not_scored";

const LEVEL_CLASSES: Record<RiskLevel, string> = {
  red: "bg-risk-red text-risk-red-foreground",
  amber: "bg-risk-amber text-risk-amber-foreground",
  green: "bg-risk-green text-risk-green-foreground",
};

/**
 * The risk board: every active placement the user may read, in the server's
 * order (red first, then falling, then lowest overall; not scored last).
 * An SME sees the technical view: the Technical score and its trend, no
 * flags and no risk filter, in the order of their Technical scores.
 */
export function RiskBoard() {
  const { user } = useAuth();
  const { rows, isLoading, error } = useRiskBoard();
  const technical =
    user?.role === "sme" || (rows ?? []).some((r) => r.view === "technical");
  const [ps, setPs] = useState(ALL);
  const [techLead, setTechLead] = useState(ALL);
  const [client, setClient] = useState(ALL);
  const [level, setLevel] = useState(ALL);

  const options = useMemo(() => filterOptions(rows ?? []), [rows]);
  const today = ukToday();

  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (r) =>
          (ps === ALL || r.ps?.id === ps) &&
          (techLead === ALL || r.tech_lead?.id === techLead) &&
          (client === ALL || r.client.id === client) &&
          (technical || level === ALL || levelKey(r) === level),
      ),
    [rows, ps, techLead, client, level, technical],
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
            cell: ({ row }) => <HealthBadge row={row.original} />,
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
          <span className="font-medium">{row.original.consultant.name}</span>
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
              label="Tech lead filter"
              all="All tech leads"
              value={techLead}
              onChange={setTechLead}
              options={options.techLeads}
            />
            <PeopleFilter
              label="Client filter"
              all="All clients"
              value={client}
              onChange={setClient}
              options={options.clients}
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
  const techLeads = new Map<string, string>();
  const clients = new Map<string, string>();
  for (const r of rows) {
    if (r.ps) ps.set(r.ps.id, r.ps.full_name ?? r.ps.email);
    if (r.tech_lead)
      techLeads.set(r.tech_lead.id, r.tech_lead.full_name ?? r.tech_lead.email);
    clients.set(r.client.id, r.client.name);
  }
  const sorted = (m: Map<string, string>): Option[] =>
    [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  return {
    ps: sorted(ps),
    techLeads: sorted(techLeads),
    clients: sorted(clients),
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

function NotScored() {
  return <span className="text-muted-foreground">Not scored</span>;
}

function HealthBadge({ row }: { row: RiskBoardRow }) {
  if (row.risk_level === null || row.overall === null) return <NotScored />;
  return (
    <Badge
      className={cn("gap-1.5 tabular-nums", LEVEL_CLASSES[row.risk_level])}
      data-testid="health-badge"
    >
      {formatScore(row.overall)}
      <span>{RISK_LEVEL_LABELS[row.risk_level]}</span>
    </Badge>
  );
}

const TREND_ICONS: Record<Trend, typeof ArrowUp> = {
  up: ArrowUp,
  flat: ArrowRight,
  down: ArrowDown,
};

function TrendIndicator({
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
          title={`${FLAG_SEVERITY_LABELS[flag.severity]}, opened ${formatDate(ukToday(new Date(flag.opened_at)))}`}
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
