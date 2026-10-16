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
import { Input } from "@/components/ui/input";
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
  type RiskLevel,
} from "@/lib/health";
import { cn } from "@/lib/utils";
import type { FlagSummary, NextAction, RiskBoardRow } from "@/types/health";

const ALL = "all";
const NOT_SCORED = "not_scored";

type LevelKey = RiskLevel | typeof NOT_SCORED;

/** The board's sections, in the server's order of levels. */
const LEVEL_KEYS: LevelKey[] = [...RISK_LEVELS, NOT_SCORED];

const LEVEL_KEY_LABELS: Record<LevelKey, string> = {
  ...RISK_LEVEL_LABELS,
  [NOT_SCORED]: "Not scored",
};

/** Each level's dot, section edge and header tint (theme tokens). */
const LEVEL_STYLES: Record<
  LevelKey,
  { dot: string; edge: string; header: string }
> = {
  red: {
    dot: "bg-risk-red",
    edge: "border-risk-red/30",
    header: "border-risk-red/20 bg-risk-red/5",
  },
  amber: {
    dot: "bg-risk-amber",
    edge: "border-risk-amber/30",
    header: "border-risk-amber/20 bg-risk-amber/5",
  },
  green: {
    dot: "bg-risk-green",
    edge: "border-risk-green/30",
    header: "border-risk-green/20 bg-risk-green/5",
  },
  [NOT_SCORED]: {
    dot: "bg-muted-foreground",
    edge: "border-border",
    header: "border-border bg-muted/50",
  },
};

/**
 * The risk board: every active placement the user may read, in the server's
 * order (red first, then falling, then lowest overall; not scored last),
 * one section per level under a strip of level counts. A count filters the
 * board to its level, as the level menu does. An SME sees the technical
 * view: one table with the Technical score and its trend, no levels, flags
 * or level filter, in the order of their Technical scores. The consultant's
 * name opens the placement page.
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
  const [search, setSearch] = useState("");

  const options = useMemo(() => filterOptions(rows ?? []), [rows]);
  const counts = useMemo(() => levelCounts(rows ?? []), [rows]);
  const today = ukToday();

  const shown = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) =>
        (ps === ALL || r.ps?.id === ps) &&
        (cdm === ALL || r.cdm?.id === cdm) &&
        (client === ALL || r.client.id === client) &&
        (stack === ALL || r.stack === stack) &&
        (technical || level === ALL || levelKey(r) === level) &&
        (query === "" || searchText(r).includes(query)),
    );
  }, [rows, ps, cdm, client, stack, level, search, technical]);

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
                <span className="font-mono font-medium tabular-nums">
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
        id: "client",
        header: "Client",
        accessorFn: (r) => r.client.name,
        cell: ({ row }) => (
          <span className="block max-w-40 whitespace-normal">
            {row.original.client.name}
          </span>
        ),
      },
      {
        id: "project",
        header: "Project",
        accessorFn: (r) => r.project.name,
        cell: ({ row }) => (
          <span className="block max-w-48 whitespace-normal">
            {row.original.project.name}
          </span>
        ),
      },
      {
        id: "weeks",
        header: "Weeks in",
        accessorFn: (r) => r.weeks_in,
        cell: ({ row }) => (
          <span className="font-mono tabular-nums">
            {row.original.weeks_in}
          </span>
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

  const emptyMessage =
    (rows ?? []).length === 0
      ? "No active placements yet. Each one appears here with its health once it is in the register."
      : "No placements match these filters.";

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {technical
          ? "Every placement you support, lowest Technical score first."
          : "Every active placement, most at risk first."}
      </p>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {!technical && rows && (
        <LevelCounts
          counts={counts}
          selected={level}
          onSelect={(key) => setLevel(level === key ? ALL : key)}
        />
      )}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card p-2.5">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search placements"
          aria-label="Search placements"
          className="w-full sm:w-64"
        />
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
            <SelectTrigger className="w-auto" aria-label="Risk level filter">
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
      </div>
      {technical || shown.length === 0 ? (
        <DataTable
          columns={columns}
          data={shown}
          isLoading={isLoading}
          sortable={false}
          searchable={false}
          searchPlaceholder="Search placements"
          emptyMessage={emptyMessage}
        />
      ) : (
        LEVEL_KEYS.map((key) => {
          const sectionRows = shown.filter((r) => levelKey(r) === key);
          return sectionRows.length === 0 ? null : (
            <LevelSection
              key={key}
              levelKey={key}
              rows={sectionRows}
              columns={columns}
            />
          );
        })
      )}
    </div>
  );
}

function levelKey(row: RiskBoardRow): LevelKey {
  return row.risk_level ?? NOT_SCORED;
}

function levelCounts(rows: RiskBoardRow[]): Record<LevelKey, number> {
  const counts: Record<LevelKey, number> = {
    red: 0,
    amber: 0,
    green: 0,
    [NOT_SCORED]: 0,
  };
  for (const r of rows) counts[levelKey(r)] += 1;
  return counts;
}

/** What the search box matches: the words the row shows. */
function searchText(r: RiskBoardRow): string {
  return [
    r.consultant.name,
    r.client.name,
    r.project.name,
    r.stack ?? "",
    LEVEL_KEY_LABELS[levelKey(r)],
    ...r.open_flags.map((f) => RISK_TRIGGER_LABELS[f.trigger]),
    r.next_action?.description ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

/** The level counts over the whole board; each one filters to its level. */
function LevelCounts({
  counts,
  selected,
  onSelect,
}: {
  counts: Record<LevelKey, number>;
  selected: string;
  onSelect: (key: LevelKey) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {LEVEL_KEYS.map((key) => (
        <button
          key={key}
          type="button"
          aria-pressed={selected === key}
          onClick={() => onSelect(key)}
          className={cn(
            "flex items-center justify-between rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
            selected === key && "border-primary ring-1 ring-primary",
          )}
          data-testid="level-count"
        >
          <span className="flex items-center gap-2 font-medium">
            <span
              className={cn("size-2.5 rounded-full", LEVEL_STYLES[key].dot)}
              aria-hidden
            />
            {LEVEL_KEY_LABELS[key]}
          </span>
          <span className="font-mono text-lg font-semibold tabular-nums">
            {counts[key]}
          </span>
        </button>
      ))}
    </div>
  );
}

/** One level's placements: a card headed by the level and its count. */
function LevelSection({
  levelKey: key,
  rows,
  columns,
}: {
  levelKey: LevelKey;
  rows: RiskBoardRow[];
  columns: ColumnDef<RiskBoardRow>[];
}) {
  const style = LEVEL_STYLES[key];
  const headingId = `risk-board-${key}`;
  return (
    <section
      aria-labelledby={headingId}
      className={cn("overflow-hidden rounded-xl border bg-card", style.edge)}
      data-testid="level-section"
    >
      <div
        className={cn(
          "flex items-center gap-2 border-b px-4 py-2.5",
          style.header,
        )}
      >
        <span className={cn("size-2.5 rounded-full", style.dot)} aria-hidden />
        <h3 id={headingId} className="text-sm font-semibold">
          {LEVEL_KEY_LABELS[key]}
        </h3>
        <span className="rounded-md bg-muted px-1.5 font-mono text-xs text-muted-foreground tabular-nums">
          {rows.length}
        </span>
      </div>
      <DataTable
        columns={columns}
        data={rows}
        sortable={false}
        searchable={false}
        framed={false}
        searchPlaceholder="Search placements"
        emptyMessage=""
      />
    </section>
  );
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
      <SelectTrigger className="w-auto" aria-label={label}>
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
    <div className="max-w-60 whitespace-normal">
      <span
        className={cn(
          "font-mono text-xs tabular-nums",
          overdue ? "font-medium text-risk-red" : "text-muted-foreground",
        )}
      >
        {formatDate(action.due_date)}
        {overdue && " · overdue"}
      </span>
      <p className="line-clamp-2" title={action.description}>
        {action.description}
      </p>
    </div>
  );
}
