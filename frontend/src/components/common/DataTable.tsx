"use client";

import { useState, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  /** Placeholder of the search box, which filters on every column's text. */
  searchPlaceholder: string;
  emptyMessage: string;
  /** Filters and buttons shown beside the search box. */
  toolbar?: ReactNode;
  isLoading?: boolean;
  /** False keeps the rows in the order given: headers do not sort. */
  sortable?: boolean;
  /** False leaves out the search box: the caller filters the rows itself. */
  searchable?: boolean;
  /** False leaves out the table's own border, for a table inside a card. */
  framed?: boolean;
  /** Tighter rows, for a long list read at a glance. */
  dense?: boolean;
  /** Extra classes for a row, e.g. to tint one that needs attention. */
  rowClassName?: (row: T) => string | undefined;
}

/**
 * A sortable, searchable table for the app's lists. The lists are small
 * (hundreds of rows at most), so sorting and filtering run in the browser.
 */
export function DataTable<T>({
  columns,
  data,
  searchPlaceholder,
  emptyMessage,
  toolbar,
  isLoading = false,
  sortable = true,
  searchable = true,
  framed = true,
  dense = false,
  rowClassName,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [search, setSearch] = useState("");

  // TanStack's hook returns functions the React Compiler cannot memoize; the
  // table is rebuilt from its inputs on every render, which is intended here.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    enableSorting: sortable,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const rows = table.getRowModel().rows;

  return (
    <div className="space-y-3">
      {(searchable || toolbar) && (
        <div className="flex flex-wrap items-center gap-2">
          {searchable && (
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              className="max-w-xs"
            />
          )}
          {toolbar}
        </div>
      )}
      <div
        className={cn(framed && "overflow-hidden rounded-xl border bg-card")}
      >
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow
                key={group.id}
                className="bg-muted/60 hover:bg-muted/60"
              >
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead
                      key={header.id}
                      className="h-9 px-3 text-xs font-semibold text-muted-foreground first:pl-4 last:pr-4"
                    >
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {sorted === "asc" && <ArrowUp className="h-3 w-3" />}
                          {sorted === "desc" && (
                            <ArrowDown className="h-3 w-3" />
                          )}
                        </button>
                      ) : (
                        flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.length > 0 ? (
              rows.map((row) => (
                <TableRow key={row.id} className={rowClassName?.(row.original)}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        "px-3 first:pl-4 last:pr-4",
                        dense ? "py-2" : "py-3",
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-20 text-center text-muted-foreground"
                >
                  {isLoading ? "Loading…" : emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
