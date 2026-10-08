"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { DataTable } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { saveRecord, useClients, useProjects } from "@/hooks/useRegister";
import { useUsers } from "@/hooks/useUsers";
import { API_ROUTES } from "@/lib/constants";
import type { Client, Project, UserListItem } from "@/types/register";
import {
  FieldGrid,
  NONE,
  SelectField,
  TextField,
  orNull,
  saveErrorMessage,
} from "./fields";
import { personOptions } from "./PlacementDialog";
import { RecordDialog } from "./RecordDialog";

const schema = z.object({
  client_id: z.string().min(1, "Choose a client"),
  name: z.string().trim().min(1, "Required").max(255),
  client_manager_name: z.string().max(255),
  tech_lead_user_id: z.string(),
  start_date: z.string(),
});

type Values = z.infer<typeof schema>;

function ProjectDialog({
  project,
  clients,
  users,
  onClose,
  onSaved,
}: {
  project: Project | null;
  clients: Client[];
  users: UserListItem[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      client_id: project?.client_id ?? "",
      name: project?.name ?? "",
      client_manager_name: project?.client_manager_name ?? "",
      tech_lead_user_id: project?.tech_lead?.id ?? NONE,
      start_date: project?.start_date ?? "",
    },
  });

  async function onSubmit(values: Values) {
    try {
      await saveRecord(API_ROUTES.projects, project?.id ?? null, {
        client_id: values.client_id,
        name: values.name,
        client_manager_name: orNull(values.client_manager_name),
        tech_lead_user_id: orNull(values.tech_lead_user_id),
        start_date: orNull(values.start_date),
      });
      toast.success(project ? "Project updated" : "Project added");
      onSaved();
      onClose();
    } catch (error) {
      form.setError("root", { message: saveErrorMessage(error) });
    }
  }

  return (
    <RecordDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={project ? "Edit project" : "Add project"}
      description="The tech lead can read every placement on the project."
      form={form}
      onSubmit={onSubmit}
    >
      <FieldGrid>
        <SelectField
          control={form.control}
          name="client_id"
          label="Client"
          options={clients.map((c) => ({ value: c.id, label: c.name }))}
        />
        <TextField control={form.control} name="name" label="Project name" />
        <TextField
          control={form.control}
          name="client_manager_name"
          label="Client manager"
        />
        <SelectField
          control={form.control}
          name="tech_lead_user_id"
          label="Tech lead"
          options={personOptions(users)}
          noneLabel="None"
        />
        <TextField
          control={form.control}
          name="start_date"
          label="Start date"
          type="date"
        />
      </FieldGrid>
    </RecordDialog>
  );
}

export function ProjectsTable() {
  const { items, isLoading, error, mutate } = useProjects(true);
  const { items: clients } = useClients(true);
  const { users } = useUsers(true);
  const [editing, setEditing] = useState<Project | null | undefined>();

  const columns = useMemo<ColumnDef<Project>[]>(
    () => [
      { accessorKey: "client_name", header: "Client" },
      { accessorKey: "name", header: "Project" },
      {
        id: "manager",
        header: "Client manager",
        accessorFn: (p) => p.client_manager_name ?? "—",
      },
      {
        id: "lead",
        header: "Tech lead",
        accessorFn: (p) => p.tech_lead?.full_name ?? "—",
      },
      { id: "start", header: "Start", accessorFn: (p) => p.start_date ?? "—" },
      {
        id: "edit",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${row.original.client_name} / ${row.original.name}`}
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
        Could not load projects: {error}
      </p>
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={items}
        isLoading={isLoading}
        searchPlaceholder="Search projects"
        emptyMessage="No projects yet."
        toolbar={
          <Button className="ml-auto" onClick={() => setEditing(null)}>
            <Plus className="mr-1 h-4 w-4" /> Add project
          </Button>
        }
      />
      {editing !== undefined && (
        <ProjectDialog
          key={editing?.id ?? "new"}
          project={editing}
          clients={clients}
          users={users}
          onClose={() => setEditing(undefined)}
          onSaved={() => void mutate()}
        />
      )}
    </>
  );
}
