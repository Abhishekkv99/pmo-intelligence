"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { saveRecord, useConsultants } from "@/hooks/useRegister";
import { useUsers } from "@/hooks/useUsers";
import { API_ROUTES } from "@/lib/constants";
import { CONSULTANT_STATUSES, humanize } from "@/lib/register";
import type { Consultant, UserListItem } from "@/types/register";
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
  full_name: z.string().trim().min(1, "Required").max(255),
  email: z.union([z.literal(""), z.email("Not an email address")]),
  phone: z.string().max(50),
  skills: z.string().max(2000),
  status: z.enum(CONSULTANT_STATUSES),
  cdm_user_id: z.string(),
});

type Values = z.infer<typeof schema>;

/** "Python, AWS ,, SQL" -> ["Python", "AWS", "SQL"] */
export function parseSkills(text: string): string[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function ConsultantDialog({
  consultant,
  users,
  onClose,
  onSaved,
}: {
  consultant: Consultant | null;
  users: UserListItem[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: consultant?.full_name ?? "",
      email: consultant?.email ?? "",
      phone: consultant?.phone ?? "",
      skills: consultant?.skills.join(", ") ?? "",
      status: consultant?.status ?? "placed",
      cdm_user_id: consultant?.cdm?.id ?? NONE,
    },
  });

  async function onSubmit(values: Values) {
    try {
      await saveRecord(API_ROUTES.consultants, consultant?.id ?? null, {
        full_name: values.full_name,
        email: orNull(values.email),
        phone: orNull(values.phone),
        skills: parseSkills(values.skills),
        status: values.status,
        cdm_user_id: orNull(values.cdm_user_id),
      });
      toast.success(consultant ? "Consultant updated" : "Consultant added");
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
      title={consultant ? "Edit consultant" : "Add consultant"}
      description="The recordings folder is matched to consultants by first or last name, so use the name people go by. The CDM can read every placement of the consultant."
      form={form}
      onSubmit={onSubmit}
    >
      <FieldGrid>
        <TextField control={form.control} name="full_name" label="Full name" />
        <TextField
          control={form.control}
          name="email"
          label="Email"
          type="email"
        />
        <TextField control={form.control} name="phone" label="Phone" />
        <SelectField
          control={form.control}
          name="status"
          label="Status"
          options={CONSULTANT_STATUSES.map((s) => ({
            value: s,
            label: humanize(s),
          }))}
        />
        <SelectField
          control={form.control}
          name="cdm_user_id"
          label="Consultant Director (CDM)"
          options={personOptions(users)}
          noneLabel="None"
        />
      </FieldGrid>
      <TextField
        control={form.control}
        name="skills"
        label="Skills"
        placeholder="Comma-separated, e.g. Python, AWS, SQL"
      />
    </RecordDialog>
  );
}

export function ConsultantsTable() {
  const { items, isLoading, error, mutate } = useConsultants(true);
  const { users } = useUsers(true);
  const [editing, setEditing] = useState<Consultant | null | undefined>();

  const columns = useMemo<ColumnDef<Consultant>[]>(
    () => [
      { accessorKey: "full_name", header: "Name" },
      { id: "email", header: "Email", accessorFn: (c) => c.email ?? "—" },
      { id: "phone", header: "Phone", accessorFn: (c) => c.phone ?? "—" },
      {
        id: "skills",
        header: "Skills",
        accessorFn: (c) => c.skills.join(", "),
      },
      {
        id: "cdm",
        header: "CDM",
        accessorFn: (c) => c.cdm?.full_name ?? "—",
      },
      {
        id: "status",
        header: "Status",
        accessorFn: (c) => c.status,
        cell: ({ row }) => (
          <Badge variant="outline">{humanize(row.original.status)}</Badge>
        ),
      },
      {
        id: "edit",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${row.original.full_name}`}
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
        Could not load consultants: {error}
      </p>
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={items}
        isLoading={isLoading}
        searchPlaceholder="Search consultants"
        emptyMessage="No consultants yet."
        toolbar={
          <Button className="ml-auto" onClick={() => setEditing(null)}>
            <Plus className="mr-1 h-4 w-4" /> Add consultant
          </Button>
        }
      />
      {editing !== undefined && (
        <ConsultantDialog
          key={editing?.id ?? "new"}
          consultant={editing}
          users={users}
          onClose={() => setEditing(undefined)}
          onSaved={() => void mutate()}
        />
      )}
    </>
  );
}
