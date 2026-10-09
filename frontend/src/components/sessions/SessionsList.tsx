"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/common/DataTable";
import { SessionStatusBadge } from "@/components/sessions/SessionStatusBadge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSessions } from "@/hooks/useSessions";
import { ROUTES } from "@/lib/constants";
import { formatUkDateTime, SESSION_STATUSES } from "@/lib/recordings";
import { humanize } from "@/lib/register";
import { formatDuration, SESSION_KIND_LABELS } from "@/lib/sessions";
import type { SessionListItem } from "@/types/sessions";

const ALL = "all";

/**
 * Every session the user may read, newest call first: PMO managers and
 * admins see all of them, everyone else those of the placements naming them.
 * A row opens the session page.
 */
export function SessionsList() {
  const { sessions, isLoading, error } = useSessions();
  const [consultant, setConsultant] = useState(ALL);
  const [status, setStatus] = useState(ALL);

  const consultants = useMemo(() => {
    const byId = new Map<string, string>();
    for (const s of sessions ?? [])
      byId.set(s.consultant.id, s.consultant.name);
    return [...byId.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [sessions]);

  const rows = useMemo(
    () =>
      (sessions ?? []).filter(
        (s) =>
          (consultant === ALL || s.consultant.id === consultant) &&
          (status === ALL || s.status === status),
      ),
    [sessions, consultant, status],
  );

  const columns = useMemo<ColumnDef<SessionListItem>[]>(
    () => [
      {
        id: "held_at",
        header: "Call (UK time)",
        accessorFn: (s) => s.held_at,
        cell: ({ row }) => (
          <Link
            href={`${ROUTES.sessions}/${row.original.id}`}
            className="font-medium underline-offset-4 hover:underline"
          >
            {formatUkDateTime(row.original.held_at)}
          </Link>
        ),
      },
      {
        id: "consultant",
        header: "Consultant",
        accessorFn: (s) => s.consultant.name,
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
          />
        ),
      },
      {
        id: "duration",
        header: "Length",
        accessorFn: (s) => s.duration_seconds ?? 0,
        cell: ({ row }) => formatDuration(row.original.duration_seconds),
      },
      {
        id: "signals",
        header: "Signals",
        accessorFn: (s) => s.signal_count,
      },
      {
        id: "actions",
        header: "Actions",
        accessorFn: (s) => s.action_count,
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
      <DataTable
        columns={columns}
        data={rows}
        isLoading={isLoading}
        searchPlaceholder="Search sessions"
        emptyMessage="No sessions yet. Recordings appear here once they are processed."
        toolbar={
          <>
            <Select value={consultant} onValueChange={setConsultant}>
              <SelectTrigger className="w-52" aria-label="Consultant filter">
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
              <SelectTrigger className="w-40" aria-label="Status filter">
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
          </>
        }
      />
    </div>
  );
}
