"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { Eye } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { quickAdd } from "@/hooks/useRegister";
import { ApiError } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import type { QuickAddOutcome, QuickAddResult } from "@/types/register";

/** The line format. Mirrors `FORMAT` in `backend/app/services/register_quick_add.py`. */
export const QUICK_ADD_FORMAT =
  "PRJ ITC <stack> - <consultant> - <client> - <start> - <end>";
const EXAMPLE =
  "PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027";

const OUTCOME_VARIANT: Record<
  QuickAddOutcome,
  "default" | "secondary" | "outline" | "destructive"
> = {
  create: "default",
  update: "secondary",
  unchanged: "outline",
  error: "destructive",
};

/**
 * Add placements as lines in the Teams chat name format. Preview runs every
 * line without writing; Confirm writes every line, or none when any line has
 * an error.
 */
export function QuickAddCard() {
  const { mutate } = useSWRConfig();
  const [text, setText] = useState("");
  const [result, setResult] = useState<QuickAddResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const lines = text.split(/\r?\n/);
  const hasLine = lines.some((line) => line.trim() !== "");

  async function run(dryRun: boolean) {
    setBusy(true);
    setError(null);
    try {
      const outcome = await quickAdd(lines, dryRun);
      setResult(outcome);
      if (outcome.applied) {
        const { created, updated } = outcome.summary;
        toast.success(`Saved: ${created} new, ${updated} updated`);
        setText("");
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
        e instanceof ApiError ? e.message : "The quick add failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const canConfirm =
    result !== null &&
    result.dry_run &&
    result.summary.errors === 0 &&
    result.summary.lines > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick add</CardTitle>
        <CardDescription>
          Paste one placement per line, as the consultant&apos;s Teams chat is
          named: <code className="text-xs">{QUICK_ADD_FORMAT}</code>. Dates are
          D/M/YYYY or D-M-YY. A new placement goes under the client&apos;s
          project &ldquo;To be confirmed&rdquo;; rename it on the Projects tab.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          aria-label="Quick add lines"
          placeholder={EXAMPLE}
          rows={3}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setResult(null);
            setError(null);
          }}
        />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!hasLine || busy} onClick={() => void run(true)}>
            <Eye className="mr-1 h-4 w-4" /> Preview
          </Button>
          <Button
            variant="secondary"
            disabled={!canConfirm || busy}
            onClick={() => void run(false)}
          >
            Confirm
          </Button>
        </div>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {result && (
          <div className="space-y-3">
            <p className="text-sm" data-testid="quick-add-summary">
              {result.applied
                ? "Saved. "
                : result.dry_run
                  ? "Preview, nothing written yet. "
                  : "Nothing was written: fix the lines with errors and preview again. "}
              {result.summary.lines} lines: {result.summary.created} new,{" "}
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
                  {result.lines.map((line) => (
                    <TableRow key={line.line}>
                      <TableCell>{line.line}</TableCell>
                      <TableCell>
                        <Badge variant={OUTCOME_VARIANT[line.outcome]}>
                          {line.outcome}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {line.consultant ? (
                          <>
                            <div className="font-medium">{line.consultant}</div>
                            <div className="text-xs text-muted-foreground">
                              {line.client} · {line.stack} · {line.start_date} →{" "}
                              {line.expected_end_date}
                            </div>
                          </>
                        ) : (
                          <div className="max-w-xs truncate text-xs text-muted-foreground">
                            {line.text}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <ul className="space-y-0.5 text-xs">
                          {line.errors.map((m) => (
                            <li key={m} className="text-destructive">
                              {m}
                            </li>
                          ))}
                          {line.changes.map((m) => (
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
      </CardContent>
    </Card>
  );
}
