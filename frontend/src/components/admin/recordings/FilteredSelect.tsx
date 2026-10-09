"use client";

import { useId, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface FilteredOption {
  value: string;
  label: string;
}

interface FilteredSelectProps {
  label: string;
  options: FilteredOption[];
  value: string | null;
  onChange: (value: string) => void;
  /** Placeholder of the filter box above the list. */
  searchPlaceholder: string;
  placeholder?: string;
}

/**
 * A select with a filter box above it, for lists too long to scroll through
 * (every placement, every consultant). Options keep their given order; the
 * chosen option stays listed even when the filter would hide it.
 */
export function FilteredSelect({
  label,
  options,
  value,
  onChange,
  searchPlaceholder,
  placeholder = "Choose…",
}: FilteredSelectProps) {
  const id = useId();
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      (o) => o.value === value || o.label.toLowerCase().includes(needle),
    );
  }, [options, filter, value]);

  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-trigger`}>{label}</Label>
      <Input
        aria-label={`Filter ${label.toLowerCase()}`}
        placeholder={searchPlaceholder}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <Select value={value ?? undefined} onValueChange={onChange}>
        <SelectTrigger id={`${id}-trigger`} className="w-full">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {shown.length === 0 ? (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">
              Nothing matches
            </div>
          ) : (
            shown.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
    </div>
  );
}
