"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { z } from "zod";
import { saveRecord } from "@/hooks/useRegister";
import { assignableUsers } from "@/hooks/useUsers";
import { API_ROUTES } from "@/lib/constants";
import {
  EXTENSION_STATUSES,
  PLACEMENT_STATUSES,
  humanize,
} from "@/lib/register";
import type {
  Consultant,
  Placement,
  Project,
  UserListItem,
} from "@/types/register";
import {
  FieldGrid,
  NONE,
  SelectField,
  TextAreaField,
  TextField,
  orNull,
  saveErrorMessage,
} from "./fields";
import { RecordDialog } from "./RecordDialog";

const schema = z
  .object({
    consultant_id: z.string().min(1, "Choose a consultant"),
    project_id: z.string().min(1, "Choose a project"),
    start_date: z.string().min(1, "Required"),
    expected_end_date: z.string(),
    extension_status: z.enum(EXTENSION_STATUSES),
    status: z.enum(PLACEMENT_STATUSES),
    rate_band: z.string().max(50),
    ps_user_id: z.string(),
    sme_user_id: z.string(),
    ended_reason: z.string().max(2000),
  })
  .refine((v) => !v.expected_end_date || v.expected_end_date >= v.start_date, {
    path: ["expected_end_date"],
    message: "Must not be before the start date",
  });

type Values = z.infer<typeof schema>;

interface PlacementDialogProps {
  /** The placement to edit, or null to create one. */
  placement: Placement | null;
  consultants: Consultant[];
  projects: Project[];
  users: UserListItem[];
  onClose: () => void;
  onSaved: () => void;
}

export function personOptions(users: UserListItem[]) {
  return assignableUsers(users).map((u) => ({
    value: u.id,
    label: `${u.full_name} (${u.role ? humanize(u.role) : "no role"})`,
  }));
}

export function PlacementDialog({
  placement,
  consultants,
  projects,
  users,
  onClose,
  onSaved,
}: PlacementDialogProps) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      consultant_id: placement?.consultant.id ?? "",
      project_id: placement?.project.id ?? "",
      start_date: placement?.start_date ?? "",
      expected_end_date: placement?.expected_end_date ?? "",
      extension_status: placement?.extension_status ?? "not_due",
      status: placement?.status ?? "active",
      rate_band: placement?.rate_band ?? "",
      ps_user_id: placement?.ps?.id ?? NONE,
      sme_user_id: placement?.sme?.id ?? NONE,
      ended_reason: placement?.ended_reason ?? "",
    },
  });

  async function onSubmit(values: Values) {
    try {
      await saveRecord(API_ROUTES.placements, placement?.id ?? null, {
        consultant_id: values.consultant_id,
        project_id: values.project_id,
        start_date: values.start_date,
        expected_end_date: orNull(values.expected_end_date),
        extension_status: values.extension_status,
        status: values.status,
        rate_band: orNull(values.rate_band),
        ps_user_id: orNull(values.ps_user_id),
        sme_user_id: orNull(values.sme_user_id),
        ended_reason: orNull(values.ended_reason),
      });
      toast.success(placement ? "Placement updated" : "Placement added");
      onSaved();
      onClose();
    } catch (error) {
      form.setError("root", { message: saveErrorMessage(error) });
    }
  }

  const people = personOptions(users);

  return (
    <RecordDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={placement ? "Edit placement" : "Add placement"}
      description="A consultant on a client project. The PS, SME and the project's tech lead can read it."
      form={form}
      onSubmit={onSubmit}
    >
      <FieldGrid>
        <SelectField
          control={form.control}
          name="consultant_id"
          label="Consultant"
          options={consultants.map((c) => ({
            value: c.id,
            label: c.full_name,
          }))}
        />
        <SelectField
          control={form.control}
          name="project_id"
          label="Project"
          options={projects.map((p) => ({
            value: p.id,
            label: `${p.client_name} / ${p.name}`,
          }))}
        />
        <TextField
          control={form.control}
          name="start_date"
          label="Start date"
          type="date"
        />
        <TextField
          control={form.control}
          name="expected_end_date"
          label="Expected end date"
          type="date"
        />
        <SelectField
          control={form.control}
          name="extension_status"
          label="Extension"
          options={EXTENSION_STATUSES.map((s) => ({
            value: s,
            label: humanize(s),
          }))}
        />
        <SelectField
          control={form.control}
          name="status"
          label="Status"
          options={PLACEMENT_STATUSES.map((s) => ({
            value: s,
            label: humanize(s),
          }))}
        />
        <SelectField
          control={form.control}
          name="ps_user_id"
          label="Placement specialist"
          options={people}
          noneLabel="None"
        />
        <SelectField
          control={form.control}
          name="sme_user_id"
          label="PMO SME"
          options={people}
          noneLabel="None"
        />
        <TextField control={form.control} name="rate_band" label="Rate band" />
      </FieldGrid>
      <TextAreaField
        control={form.control}
        name="ended_reason"
        label="Ended reason"
      />
    </RecordDialog>
  );
}
