"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { DataTable } from "@/components/common/DataTable";
import { useAuth } from "@/components/providers/AuthProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FieldGrid,
  NONE,
  SelectField,
  TextField,
  saveErrorMessage,
} from "@/components/admin/register/fields";
import { RecordDialog } from "@/components/admin/register/RecordDialog";
import { changeRole, grantRole, useUsers } from "@/hooks/useUsers";
import { ROLES, ROLE_LABELS, roleLabel, type Role } from "@/lib/roles";
import type { UserListItem } from "@/types/register";

const ROLE_OPTIONS = ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }));

const grantSchema = z.object({
  email: z.email("Not an email address"),
  role: z.enum(ROLES, "Choose a role"),
});

const changeSchema = z.object({ role: z.string().min(1, "Choose a role") });

function GrantDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<z.infer<typeof grantSchema>>({
    resolver: zodResolver(grantSchema),
    defaultValues: { email: "", role: undefined },
  });

  return (
    <RecordDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Give someone access"
      description="They can sign in with Microsoft once they have a role. Someone who has never signed in is added by email and linked at their first sign-in."
      form={form}
      onSubmit={async (values) => {
        try {
          const result = await grantRole(values.email, values.role);
          toast.success(result.message);
          onSaved();
          onClose();
        } catch (error) {
          form.setError("root", { message: saveErrorMessage(error) });
        }
      }}
    >
      <FieldGrid>
        <TextField
          control={form.control}
          name="email"
          label="Email"
          type="email"
        />
        <SelectField
          control={form.control}
          name="role"
          label="Role"
          options={ROLE_OPTIONS}
        />
      </FieldGrid>
    </RecordDialog>
  );
}

function ChangeRoleDialog({
  user,
  onClose,
  onSaved,
}: {
  user: UserListItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<z.infer<typeof changeSchema>>({
    resolver: zodResolver(changeSchema),
    defaultValues: { role: user.role ?? NONE },
  });

  return (
    <RecordDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Role of ${user.full_name}`}
      description="Removing the role ends their sessions: an open page stops working within 15 minutes. The last active PMO manager keeps the role."
      form={form}
      onSubmit={async (values) => {
        const role = values.role === NONE ? null : (values.role as Role);
        try {
          const result = await changeRole(user.id, role);
          toast.success(result.message);
          onSaved();
          onClose();
        } catch (error) {
          form.setError("root", { message: saveErrorMessage(error) });
        }
      }}
    >
      <SelectField
        control={form.control}
        name="role"
        label="Role"
        options={ROLE_OPTIONS}
        noneLabel="No role (no access)"
      />
    </RecordDialog>
  );
}

/** Who may sign in, and with which role. For PMO managers and admins. */
export function UsersTab() {
  const { user: me } = useAuth();
  const { users, isLoading, error, mutate } = useUsers(true);
  const [granting, setGranting] = useState(false);
  const [editing, setEditing] = useState<UserListItem | null>(null);

  const columns = useMemo<ColumnDef<UserListItem>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        accessorFn: (u) => `${u.full_name} ${u.email}`,
        cell: ({ row }) => (
          <div>
            <div className="font-medium">
              {row.original.full_name}
              {row.original.id === me?.id && (
                <span className="ml-1 text-xs text-muted-foreground">
                  (you)
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              {row.original.email}
            </div>
          </div>
        ),
      },
      {
        id: "role",
        header: "Role",
        accessorFn: (u) => roleLabel(u.role),
        cell: ({ row }) => (
          <Badge variant={row.original.role ? "default" : "outline"}>
            {roleLabel(row.original.role)}
          </Badge>
        ),
      },
      {
        id: "active",
        header: "Account",
        accessorFn: (u) => (u.is_active ? "Active" : "Disabled"),
      },
      {
        id: "signin",
        header: "Microsoft sign-in",
        accessorFn: (u) =>
          u.signed_in_with_microsoft ? "Signed in" : "Not yet",
      },
      {
        id: "edit",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Change the role of ${row.original.full_name}`}
            onClick={() => setEditing(row.original)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
        ),
      },
    ],
    [me?.id],
  );

  if (error) {
    return (
      <p className="text-sm text-destructive">Could not load users: {error}</p>
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={users}
        isLoading={isLoading}
        searchPlaceholder="Search users"
        emptyMessage="No users yet."
        toolbar={
          <Button className="ml-auto" onClick={() => setGranting(true)}>
            <Plus className="mr-1 h-4 w-4" /> Give access
          </Button>
        }
      />
      {granting && (
        <GrantDialog
          onClose={() => setGranting(false)}
          onSaved={() => void mutate()}
        />
      )}
      {editing && (
        <ChangeRoleDialog
          key={editing.id}
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => void mutate()}
        />
      )}
    </>
  );
}
