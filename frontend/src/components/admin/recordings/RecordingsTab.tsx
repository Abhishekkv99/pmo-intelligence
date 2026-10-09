"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Link2, Pencil, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";
import { DataTable } from "@/components/common/DataTable";
import { saveErrorMessage } from "@/components/admin/register/fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requestScan, useRecordings } from "@/hooks/useRecordings";
import {
  formatBytes,
  formatUkDateTime,
  formatUsd,
  recordingRows,
  type RecordingRow,
} from "@/lib/recordings";
import { humanize } from "@/lib/register";
import type { RecordingFolder, RecordingFolderList } from "@/types/recordings";
import {
  ChooseConsultantDialog,
  ProcessDialog,
  UploadSessionDialog,
  UrlSessionDialog,
} from "./dialogs";

function ScanSummaryLine({ list }: { list: RecordingFolderList }) {
  const scan = list.latest_scan;
  const schedule = list.scan_enabled
    ? `Scanned automatically every ${Math.round(list.scan_interval_seconds / 60)} minutes.`
    : "Automatic scan is off.";
  if (!scan) {
    return (
      <p className="text-sm text-muted-foreground">No scan yet. {schedule}</p>
    );
  }
  const when = formatUkDateTime(scan.finished_at ?? scan.started_at);
  if (scan.status === "failed") {
    return (
      <p className="text-sm text-destructive">
        Last scan failed at {when}: {scan.error_message ?? "no reason given"}.{" "}
        {schedule}
      </p>
    );
  }
  if (scan.status === "running") {
    return (
      <p className="text-sm text-muted-foreground">
        A scan is running (started {when}). {schedule}
      </p>
    );
  }
  return (
    <p className="text-sm text-muted-foreground">
      Last scan {when}: {scan.folders_seen} folders, {scan.recordings_seen}{" "}
      recordings ({scan.recordings_added} new). {schedule}
    </p>
  );
}

function StatusCell({ row }: { row: RecordingRow }) {
  const session = row.recording.session;
  if (!session) {
    return <span className="text-sm text-muted-foreground">Not processed</span>;
  }
  if (session.status === "failed") {
    return (
      <Badge variant="destructive" title={session.error_message ?? undefined}>
        Failed
      </Badge>
    );
  }
  return <Badge variant="secondary">{humanize(session.status)}</Badge>;
}

/**
 * Admin > Recordings: the PMO recordings folder. Folders that name several
 * consultants wait for a choice at the top; below, every cataloged recording,
 * newest call first, with Process. Upload and URL add a recording by hand.
 */
export function RecordingsTab({ enabled }: { enabled: boolean }) {
  const { list, isLoading, error, mutate } = useRecordings(enabled);
  const [choosing, setChoosing] = useState<RecordingFolder | null>(null);
  const [processing, setProcessing] = useState<RecordingRow | null>(null);
  const [adding, setAdding] = useState<"upload" | "url" | null>(null);
  const [scanning, setScanning] = useState(false);

  const rows = useMemo(() => recordingRows(list?.folders ?? []), [list]);
  const undecided = useMemo(
    () =>
      (list?.folders ?? []).filter((f) => f.match_status === "needs_choice"),
    [list],
  );

  const columns = useMemo<ColumnDef<RecordingRow>[]>(
    () => [
      {
        id: "call",
        header: "Call (UK time)",
        accessorFn: (r) => r.recording.recorded_at,
        cell: ({ row }) => (
          <div>
            <div>{formatUkDateTime(row.original.recording.recorded_at)}</div>
            {!row.original.recording.time_from_name && (
              <div className="text-xs text-muted-foreground">
                file time, not in the name
              </div>
            )}
          </div>
        ),
      },
      {
        id: "consultant",
        header: "Consultant / folder",
        accessorFn: (r) =>
          `${r.folder.consultant?.full_name ?? ""} ${r.folder.display_name}`,
        cell: ({ row }) => {
          const folder = row.original.folder;
          return (
            <div className="flex items-start gap-1">
              <div>
                <div className="font-medium">
                  {folder.consultant?.full_name ?? (
                    <span className="text-muted-foreground">
                      Choose a consultant
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {folder.display_name || "(no name)"}
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label={`Change the consultant of ${folder.display_name || "this folder"}`}
                onClick={() => setChoosing(folder)}
              >
                <Pencil className="size-3.5" />
              </Button>
            </div>
          );
        },
      },
      {
        id: "size",
        header: "Size / estimate",
        accessorFn: (r) => r.recording.size_bytes,
        cell: ({ row }) => {
          const r = row.original.recording;
          return (
            <div className="text-sm">
              {formatBytes(r.size_bytes)}
              <div className="text-xs text-muted-foreground">
                about {Math.round(r.estimated_minutes)} min,{" "}
                {formatUsd(r.estimated_cost_usd)}
              </div>
            </div>
          );
        },
      },
      {
        id: "status",
        header: "Status",
        accessorFn: (r) => r.recording.session?.status ?? "not processed",
        cell: ({ row }) => <StatusCell row={row.original} />,
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          const { recording, folder } = row.original;
          const decided = folder.consultant !== null;
          return recording.session ? null : (
            <Button
              size="sm"
              disabled={!decided}
              title={
                decided ? undefined : "Choose the folder's consultant first"
              }
              onClick={() => setProcessing(row.original)}
            >
              Process
            </Button>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          {list ? (
            <ScanSummaryLine list={list} />
          ) : (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={scanning}
            onClick={async () => {
              setScanning(true);
              try {
                const { queued } = await requestScan();
                toast.success(
                  queued
                    ? "Scan queued; new recordings appear in a minute or two"
                    : "A scan is already queued or running",
                );
              } catch (err) {
                toast.error(saveErrorMessage(err));
              } finally {
                setScanning(false);
              }
            }}
          >
            <RefreshCw className="size-4" />
            Scan now
          </Button>
          <Button variant="outline" onClick={() => setAdding("url")}>
            <Link2 className="size-4" />
            Add from URL
          </Button>
          <Button onClick={() => setAdding("upload")}>
            <Upload className="size-4" />
            Upload recording
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {undecided.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Folders naming more than one consultant
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {undecided.map((folder) => (
              <div
                key={folder.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0 last:pb-0"
              >
                <div>
                  <div className="font-medium">
                    {folder.display_name || "(no name)"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Could be{" "}
                    {folder.candidates.map((c) => c.full_name).join(" or ")}
                    {" · "}
                    {folder.recordings.length} recordings
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setChoosing(folder)}
                >
                  Choose consultant
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <DataTable
        columns={columns}
        data={rows}
        searchPlaceholder="Search consultant, folder, status"
        emptyMessage="No recordings yet. A folder appears once the register holds a consultant it names."
        isLoading={isLoading}
      />

      {choosing && (
        <ChooseConsultantDialog
          folder={choosing}
          onClose={() => setChoosing(null)}
          onSaved={() => void mutate()}
        />
      )}
      {processing && (
        <ProcessDialog
          row={processing}
          onClose={() => setProcessing(null)}
          onQueued={() => void mutate()}
        />
      )}
      {adding === "upload" && (
        <UploadSessionDialog
          onClose={() => setAdding(null)}
          onCreated={() => void mutate()}
        />
      )}
      {adding === "url" && (
        <UrlSessionDialog
          onClose={() => setAdding(null)}
          onCreated={() => void mutate()}
        />
      )}
    </div>
  );
}
