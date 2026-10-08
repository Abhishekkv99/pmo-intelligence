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
import { saveRecord, useClients } from "@/hooks/useRegister";
import { API_ROUTES } from "@/lib/constants";
import type { Client } from "@/types/register";
import { FieldGrid, TextField, orNull, saveErrorMessage } from "./fields";
import { RecordDialog } from "./RecordDialog";

const schema = z.object({
  name: z.string().trim().min(1, "Required").max(255),
  industry: z.string().max(255),
});

type Values = z.infer<typeof schema>;

function ClientDialog({
  client,
  onClose,
  onSaved,
}: {
  client: Client | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: client?.name ?? "",
      industry: client?.industry ?? "",
    },
  });

  async function onSubmit(values: Values) {
    try {
      await saveRecord(API_ROUTES.clients, client?.id ?? null, {
        name: values.name,
        industry: orNull(values.industry),
      });
      toast.success(client ? "Client updated" : "Client added");
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
      title={client ? "Edit client" : "Add client"}
      description="Client names are unique, ignoring case and spacing."
      form={form}
      onSubmit={onSubmit}
    >
      <FieldGrid>
        <TextField control={form.control} name="name" label="Name" />
        <TextField control={form.control} name="industry" label="Industry" />
      </FieldGrid>
    </RecordDialog>
  );
}

export function ClientsTable() {
  const { items, isLoading, error, mutate } = useClients(true);
  const [editing, setEditing] = useState<Client | null | undefined>();

  const columns = useMemo<ColumnDef<Client>[]>(
    () => [
      { accessorKey: "name", header: "Name" },
      {
        id: "industry",
        header: "Industry",
        accessorFn: (c) => c.industry ?? "—",
      },
      {
        id: "edit",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${row.original.name}`}
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
        Could not load clients: {error}
      </p>
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={items}
        isLoading={isLoading}
        searchPlaceholder="Search clients"
        emptyMessage="No clients yet."
        toolbar={
          <Button className="ml-auto" onClick={() => setEditing(null)}>
            <Plus className="mr-1 h-4 w-4" /> Add client
          </Button>
        }
      />
      {editing !== undefined && (
        <ClientDialog
          key={editing?.id ?? "new"}
          client={editing}
          onClose={() => setEditing(undefined)}
          onSaved={() => void mutate()}
        />
      )}
    </>
  );
}
