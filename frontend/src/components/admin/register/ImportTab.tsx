"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { Download, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { importRegister } from "@/hooks/useRegister";
import { ApiError } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import type { ImportOutcome, ImportResult } from "@/types/register";

/** The CSV columns, in order. Mirrors `COLUMNS` in `backend/app/services/register_import.py`. */
export const IMPORT_COLUMNS = [
  "consultant_full_name",
  "consultant_email",
  "client_name",
  "project_name",
  "client_manager_name",
  "tech_lead_email",
  "ps_email",
  "sme_email",
  "start_date",
  "expected_end_date",
  "extension_status",
  "rate_band",
] as const;

const OUTCOME_VARIANT: Record<
  ImportOutcome,
  "default" | "secondary" | "outline" | "destructive"
> = {
  create: "default",
  update: "secondary",
  unchanged: "outline",
  error: "destructive",
};

function downloadTemplate() {
  const blob = new Blob([IMPORT_COLUMNS.join(",") + "\r\n"], {
    type: "text/csv",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "register-template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Seed or update the register from a CSV, one row per placement. Preview
 * runs the whole file without writing; Confirm writes every row, or none
 * when any row has an error.
 */
export function ImportTab() {
  const { mutate } = useSWRConfig();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const outcome = await importRegister(file, dryRun);
      setResult(outcome);
      if (outcome.applied) {
        toast.success(`Imported ${outcome.summary.rows} rows`);
        for (const key of [
          API_ROUTES.placements,
          API_ROUTES.consultants,
          API_ROUTES.clients,
          API_ROUTES.projects,
        ]) {
          void mutate(key);
        }
      }
    } catch (e) {
      setResult(null);
      setError(
        e instanceof ApiError ? e.message : "The import failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const canConfirm =
    result !== null &&
    result.dry_run &&
    result.summary.errors === 0 &&
    result.summary.rows > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Import the register from a CSV</CardTitle>
          <CardDescription>
            One row per placement. A filled cell overwrites the stored value; an
            empty cell keeps it. People (tech lead, PS, SME) are named by the
            email of a user who already has a role. Dates are YYYY-MM-DD or
            DD/MM/YYYY.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          <Input
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            className="max-w-sm"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
              setError(null);
            }}
          />
          <Button disabled={!file || busy} onClick={() => void run(true)}>
            <Upload className="mr-1 h-4 w-4" /> Preview
          </Button>
          <Button
            variant="secondary"
            disabled={!canConfirm || busy}
            onClick={() => void run(false)}
          >
            Confirm import
          </Button>
          <Button
            variant="ghost"
            className="ml-auto"
            onClick={downloadTemplate}
          >
            <Download className="mr-1 h-4 w-4" /> Template
          </Button>
        </CardContent>
      </Card>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-3">
          <p className="text-sm" data-testid="import-summary">
            {result.applied
              ? "Imported. "
              : result.dry_run
                ? "Preview, nothing written yet. "
                : "Nothing was written: fix the rows with errors and preview again. "}
            {result.summary.rows} rows: {result.summary.created} new,{" "}
            {result.summary.updated} updated, {result.summary.unchanged}{" "}
            unchanged, {result.summary.errors} with errors.
          </p>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Line</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Placement</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.rows.map((row) => (
                  <TableRow key={row.row}>
                    <TableCell>{row.row}</TableCell>
                    <TableCell>
                      <Badge variant={OUTCOME_VARIANT[row.outcome]}>
                        {row.outcome}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{row.consultant ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.client ?? "—"} / {row.project ?? "—"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <ul className="space-y-0.5 text-xs">
                        {row.errors.map((m) => (
                          <li key={m} className="text-destructive">
                            {m}
                          </li>
                        ))}
                        {row.warnings.map((m) => (
                          <li
                            key={m}
                            className="text-amber-600 dark:text-amber-400"
                          >
                            {m}
                          </li>
                        ))}
                        {row.changes.map((m) => (
                          <li key={m} className="text-muted-foreground">
                            {m}
                          </li>
                        ))}
                      </ul>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}
