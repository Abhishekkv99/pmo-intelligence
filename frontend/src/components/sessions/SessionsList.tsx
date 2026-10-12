"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/common/DataTable";
import { SessionStatusBadge } from "@/components/sessions/SessionStatusBadge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSessions } from "@/hooks/useSessions";
import { ROUTES } from "@/lib/constants";
import { placementPath } from "@/lib/health";
import { formatUkDateTime, SESSION_STATUSES } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import { formatDuration, SESSION_KIND_LABELS } from "@/lib/sessions";
import type { SessionListItem } from "@/types/sessions";

const ALL = "all";

/**
 * Every session the user may read, newest call first: PMO managers and
 * admins see all of them, everyone else those of the placements naming them.
 * The call time opens the session page; the consultant's name opens the
 * placement page. A failed call's row is tinted, its reason on hover.
 */
export function SessionsList() {
  const { sessions, isLoading, error } = useSessions();
  const [consultant, setConsultant] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [search, setSearch] = useState("");

  const consultants = useMemo(() => {
    const byId = new Map<string, string>();
    for (const s of sessions ?? [])
      byId.set(s.consultant.id, s.consultant.name);
    return [...byId.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [sessions]);

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (sessions ?? []).filter(
      (s) =>
        (consultant === ALL || s.consultant.id === consultant) &&
        (status === ALL || s.status === status) &&
        (query === "" || searchText(s).includes(query)),
    );
  }, [sessions, consultant, status, search]);

  const columns = useMemo<ColumnDef<SessionListItem>[]>(
    () => [
      {
        id: "held_at",
        header: "Call (UK time)",
        accessorFn: (s) => s.held_at,
        cell: ({ row }) => (
          <Link
            href={`${ROUTES.sessions}/${row.original.id}`}
            className="font-mono text-xs font-medium whitespace-nowrap underline-offset-4 hover:underline"
          >
            {formatUkDateTime(row.original.held_at)}
          </Link>
        ),
      },
      {
        id: "consultant",
        header: "Consultant",
        accessorFn: (s) => s.consultant.name,
        cell: ({ row }) => (
          <Link
            href={placementPath(row.original.placement_id)}
            className="underline-offset-4 hover:underline"
          >
            {row.original.consultant.name}
          </Link>
        ),
      },
      {
        id: "placement",
        header: "Client · project",
        accessorFn: (s) => `${s.client.name} · ${s.project.name}`,
      },
      {
        id: "kind",
        header: "Kind",
        accessorFn: (s) => (s.kind ? SESSION_KIND_LABELS[s.kind] : ""),
        cell: ({ row }) =>
          row.original.kind ? (
            SESSION_KIND_LABELS[row.original.kind]
          ) : (
            <span className="text-muted-foreground">Not classified</span>
          ),
      },
      {
        id: "status",
        header: "Status",
        accessorFn: (s) => s.status,
        cell: ({ row }) => (
          <SessionStatusBadge
            status={row.original.status}
            reason={row.original.error_message}
            variant="dot"
          />
        ),
      },
      {
        id: "duration",
        header: "Length",
        accessorFn: (s) => s.duration_seconds ?? 0,
        cell: ({ row }) => (
          <span className="font-mono text-xs whitespace-nowrap">
            {formatDuration(row.original.duration_seconds)}
          </span>
        ),
      },
      {
        id: "signals",
        header: "Signals",
        accessorFn: (s) => s.signal_count,
        cell: ({ row }) => (
          <span className="font-mono tabular-nums">
            {row.original.signal_count}
          </span>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        accessorFn: (s) => s.action_count,
        cell: ({ row }) => (
          <span className="font-mono tabular-nums">
            {row.original.action_count}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card p-2.5">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search sessions"
          aria-label="Search sessions"
          className="w-full sm:w-64"
        />
        <Select value={consultant} onValueChange={setConsultant}>
          <SelectTrigger className="w-auto" aria-label="Consultant filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All consultants</SelectItem>
            {consultants.map(([id, name]) => (
              <SelectItem key={id} value={id}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-auto" aria-label="Status filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {SESSION_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <DataTable
        columns={columns}
        data={rows}
        isLoading={isLoading}
        searchable={false}
        dense
        searchPlaceholder="Search sessions"
        emptyMessage={
          (sessions ?? []).length === 0
            ? "No sessions yet. Recordings appear here once they are processed."
            : "No sessions match these filters."
        }
        rowClassName={(s) =>
          s.status === "failed"
            ? "bg-destructive/5 hover:bg-destructive/10"
            : undefined
        }
      />
    </div>
  );
}

/** What the search box matches: the words the row shows. */
function searchText(s: SessionListItem): string {
  return [
    s.consultant.name,
    s.client.name,
    s.project.name,
    s.kind ? SESSION_KIND_LABELS[s.kind] : "Not classified",
    humanize(s.status),
  ]
    .join(" ")
    .toLowerCase();
}
