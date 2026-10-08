"use client";

import type { ReactNode } from "react";
import type { Control, FieldPath, FieldValues } from "react-hook-form";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";

/** Radix Select cannot hold an empty value, so "none" is this sentinel. */
export const NONE = "__none__";

/** A form string as the API wants it: empty or NONE becomes null. */
export function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" || trimmed === NONE ? null : trimmed;
}

/** The message to show for a failed save: the API's own, when it sent one. */
export function saveErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Could not save. Try again.";
}

interface FieldProps<T extends FieldValues> {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
}

export function TextField<T extends FieldValues>({
  control,
  name,
  label,
  type = "text",
  placeholder,
}: FieldProps<T> & { type?: "text" | "email" | "date"; placeholder?: string }) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input type={type} placeholder={placeholder} {...field} />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export function TextAreaField<T extends FieldValues>({
  control,
  name,
  label,
}: FieldProps<T>) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Textarea rows={3} {...field} />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export interface Option {
  value: string;
  label: string;
}

export function SelectField<T extends FieldValues>({
  control,
  name,
  label,
  options,
  noneLabel,
  placeholder = "Choose…",
}: FieldProps<T> & {
  options: Option[];
  /** When set, the list starts with a "none" choice under this label. */
  noneLabel?: string;
  placeholder?: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select
            value={field.value || undefined}
            onValueChange={field.onChange}
          >
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={placeholder} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {noneLabel !== undefined && (
                <SelectItem value={NONE}>{noneLabel}</SelectItem>
              )}
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** The two-column grid the register dialogs lay their fields out in. */
export function FieldGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2">{children}</div>;
}
