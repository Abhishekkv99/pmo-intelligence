"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Pencil, Plus } from "lucide-react";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useConsultants,
  usePlacements,
  useProjects,
} from "@/hooks/useRegister";
import { useUsers } from "@/hooks/useUsers";
import { PLACEMENT_STATUSES, humanize } from "@/lib/register";
import type { PersonRef, Placement } from "@/types/register";
import { PlacementDialog } from "./PlacementDialog";

const ALL = "all";

function personName(person: PersonRef | null): string {
  return person?.full_name ?? "—";
}

export function PlacementsTable() {
  const { items, isLoading, error, mutate } = usePlacements(true);
  const { items: consultants } = useConsultants(true);
  const { items: projects } = useProjects(true);
  const { users } = useUsers(true);
  const [status, setStatus] = useState<string>("active");
  // undefined: closed; null: adding; a placement: editing it
  const [editing, setEditing] = useState<Placement | null | undefined>();

  const visible = useMemo(
    () => (status === ALL ? items : items.filter((p) => p.status === status)),
    [items, status],
  );

  const columns = useMemo<ColumnDef<Placement>[]>(
    () => [
      {
        id: "consultant",
        header: "Consultant",
        accessorFn: (p) =>
          `${p.consultant.full_name} ${p.consultant.email ?? ""}`,
        cell: ({ row }) => (
          <div>
            <div className="font-medium">
              {row.original.consultant.full_name}
            </div>
            <div className="text-xs text-muted-foreground">
              {row.original.consultant.email ?? "no email"}
            </div>
          </div>
        ),
      },
      { id: "client", header: "Client", accessorFn: (p) => p.client.name },
      { id: "project", header: "Project", accessorFn: (p) => p.project.name },
      {
        id: "stack",
        header: "Stack",
        accessorFn: (p) => p.stack ?? "—",
      },
      {
        id: "dates",
        header: "Dates",
        accessorFn: (p) => p.start_date,
        cell: ({ row }) =>
          `${row.original.start_date} → ${row.original.expected_end_date ?? "open"}`,
      },
      {
        id: "extension",
        header: "Extension",
        accessorFn: (p) => p.extension_status,
        cell: ({ row }) => (
          <Badge variant="outline">
            {humanize(row.original.extension_status)}
          </Badge>
        ),
      },
      {
        id: "status",
        header: "Status",
        accessorFn: (p) => p.status,
        cell: ({ row }) => (
          <Badge
            variant={row.original.status === "active" ? "default" : "secondary"}
          >
            {humanize(row.original.status)}
          </Badge>
        ),
      },
      { id: "ps", header: "PS", accessorFn: (p) => personName(p.ps) },
      { id: "sme", header: "SME", accessorFn: (p) => personName(p.sme) },
      {
        id: "lead",
        header: "CDM",
        accessorFn: (p) => personName(p.cdm),
      },
      {
        id: "edit",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit placement of ${row.original.consultant.full_name}`}
            onClick={() => setEditing(row.original)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
        ),
      },
    ],
    [],
  );

  if (error) {
    return (
      <p className="text-sm text-destructive">
        Could not load placements: {error}
      </p>
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={visible}
        isLoading={isLoading}
        searchPlaceholder="Search placements"
        emptyMessage="No placements yet. Add one, or paste a line in Quick add."
        toolbar={
          <>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-40" aria-label="Status filter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All statuses</SelectItem>
                {PLACEMENT_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {humanize(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button className="ml-auto" onClick={() => setEditing(null)}>
              <Plus className="mr-1 h-4 w-4" /> Add placement
            </Button>
          </>
        }
      />
      {editing !== undefined && (
        <PlacementDialog
          key={editing?.id ?? "new"}
          placement={editing}
          consultants={consultants}
          projects={projects}
          users={users}
          onClose={() => setEditing(undefined)}
          onSaved={() => void mutate()}
        />
      )}
    </>
  );
}
