"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface DateRangeFilterProps {
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onClear: () => void;
}

export function DateRangeFilter({
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  onClear,
}: DateRangeFilterProps) {
  const hasFilter = dateFrom !== "" || dateTo !== "";

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <label
          htmlFor="date-range-from"
          className="text-sm text-muted-foreground whitespace-nowrap"
        >
          From
        </label>
        <Input
          id="date-range-from"
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="w-[160px]"
        />
      </div>
      <div className="flex items-center gap-2">
        <label
          htmlFor="date-range-to"
          className="text-sm text-muted-foreground whitespace-nowrap"
        >
          To
        </label>
        <Input
          id="date-range-to"
          type="date"
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          className="w-[160px]"
        />
      </div>
      {hasFilter && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear dates
        </Button>
      )}
    </div>
  );
}
