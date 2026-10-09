"use client";

import { useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { FileDropZone } from "@/components/common/FileDropZone";
import { UploadProgress } from "@/components/common/UploadProgress";
import { saveErrorMessage } from "@/components/admin/register/fields";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  chooseFolderConsultant,
  processRecording,
} from "@/hooks/useRecordings";
import { useConsultants, usePlacements } from "@/hooks/useRegister";
import {
  formatBytes,
  formatUkDateTime,
  formatUsd,
  heldAtFromFilename,
  ukLocalToIso,
  type RecordingRow,
} from "@/lib/recordings";
import { humanize } from "@/lib/register";
import {
  MAX_UPLOAD_MB,
  RECORDING_ACCEPT,
  sessionFromUrl,
  uploadSession,
} from "@/lib/upload";
import type { PlacementOption, RecordingFolder } from "@/types/recordings";
import type { Placement } from "@/types/register";
import { FilteredSelect, type FilteredOption } from "./FilteredSelect";

interface DialogShellProps {
  title: string;
  description: ReactNode;
  onClose: () => void;
  error: string | null;
  busy: boolean;
  submitLabel: string;
  busyLabel: string;
  canSubmit: boolean;
  onSubmit: () => void;
  children?: ReactNode;
}

function DialogShell({
  title,
  description,
  onClose,
  error,
  busy,
  submitLabel,
  busyLabel,
  canSubmit,
  onSubmit,
  children,
}: DialogShellProps) {
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <div>{description}</div>
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          {children}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !canSubmit}>
              {busy ? busyLabel : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Choosing a folder's consultant -------------------------------------------

export function ChooseConsultantDialog({
  folder,
  onClose,
  onSaved,
}: {
  folder: RecordingFolder;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { items: consultants } = useConsultants(true);
  const [consultantId, setConsultantId] = useState<string | null>(
    folder.consultant?.id ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The scan's candidates first, then everyone else in the register.
  const options = useMemo<FilteredOption[]>(() => {
    const candidateIds = new Set(folder.candidates.map((c) => c.id));
    const first = folder.candidates.map((c) => ({
      value: c.id,
      label: `${c.full_name} (named in the folder)`,
    }));
    const rest = consultants
      .filter((c) => !candidateIds.has(c.id))
      .map((c) => ({
        value: c.id,
        label: c.email ? `${c.full_name} (${c.email})` : c.full_name,
      }));
    return [...first, ...rest];
  }, [consultants, folder.candidates]);

  return (
    <DialogShell
      title="Whose recordings are these?"
      description={
        <>
          <span className="font-medium">
            {folder.display_name || "(no name)"}
          </span>
          . Later scans keep this choice. Sessions already made from the folder
          keep their placement.
        </>
      }
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Save"
      busyLabel="Saving…"
      canSubmit={consultantId !== null}
      onSubmit={async () => {
        if (!consultantId) return;
        setBusy(true);
        setError(null);
        try {
          await chooseFolderConsultant(folder.id, consultantId);
          toast.success("Consultant saved for this folder");
          onSaved();
          onClose();
        } catch (err) {
          setError(saveErrorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <FilteredSelect
        label="Consultant"
        options={options}
        value={consultantId}
        onChange={setConsultantId}
        searchPlaceholder="Search by name or email"
      />
    </DialogShell>
  );
}

// --- Process ------------------------------------------------------------------

function placementLabel(p: PlacementOption): string {
  const end = p.expected_end_date ?? "open";
  return `${p.client_name} / ${p.project_name}, ${p.start_date} → ${end} (${humanize(p.status)})`;
}

export function ProcessDialog({
  row,
  onClose,
  onQueued,
}: {
  row: RecordingRow;
  onClose: () => void;
  onQueued: () => void;
}) {
  const { recording, folder } = row;
  const [choice, setChoice] = useState<{
    detail: string;
    placements: PlacementOption[];
  } | null>(null);
  const [placementId, setPlacementId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const placementOptions = useMemo<FilteredOption[]>(
    () =>
      (choice?.placements ?? []).map((p) => ({
        value: p.id,
        label: placementLabel(p),
      })),
    [choice],
  );

  return (
    <DialogShell
      title="Process this recording?"
      description={
        <div className="space-y-1">
          <div>
            {folder.consultant?.full_name ?? "Unknown consultant"},{" "}
            {formatUkDateTime(recording.recorded_at)}
            {!recording.time_from_name && " (file time)"}
          </div>
          <div className="text-xs">{recording.filename}</div>
          <div>
            {formatBytes(recording.size_bytes)}: about{" "}
            {Math.round(recording.estimated_minutes)} minutes, about{" "}
            <span className="font-medium">
              {formatUsd(recording.estimated_cost_usd)}
            </span>{" "}
            to transcribe (estimated from the file size).
          </div>
        </div>
      }
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel={choice ? "Process with this placement" : "Process"}
      busyLabel="Queuing…"
      canSubmit={!choice || placementId !== null}
      onSubmit={async () => {
        setBusy(true);
        setError(null);
        try {
          const outcome = await processRecording(recording.id, placementId);
          if (outcome.kind === "choose") {
            setChoice(outcome.choice);
            setPlacementId(null);
            return;
          }
          toast.success("Queued for transcription");
          onQueued();
          onClose();
        } catch (err) {
          setError(saveErrorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {choice && (
        <div className="space-y-2">
          <p className="text-sm">{choice.detail}</p>
          <FilteredSelect
            label="Placement"
            options={placementOptions}
            value={placementId}
            onChange={setPlacementId}
            searchPlaceholder="Search by client or project"
          />
        </div>
      )}
    </DialogShell>
  );
}

// --- Upload and URL -----------------------------------------------------------

/** The last path segment of a URL, decoded; empty when it cannot be read. */
function urlFilename(url: string): string {
  const last = url.split("?")[0].split("/").pop() ?? "";
  try {
    return decodeURIComponent(last);
  } catch {
    return last;
  }
}

/** Every placement, active ones first, newest start first within each. */
function placementChoices(placements: Placement[]): FilteredOption[] {
  return [...placements]
    .sort(
      (a, b) =>
        Number(b.status === "active") - Number(a.status === "active") ||
        b.start_date.localeCompare(a.start_date),
    )
    .map((p) => ({
      value: p.id,
      label: `${p.consultant.full_name}: ${p.client.name} / ${p.project.name}, from ${p.start_date}${
        p.status === "active" ? "" : ` (${humanize(p.status)})`
      }`,
    }));
}

function HeldAtField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="held-at">When was the call? (UK time)</Label>
      <Input
        id="held-at"
        type="datetime-local"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export function UploadSessionDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { items: placements } = usePlacements(true);
  const options = useMemo(() => placementChoices(placements), [placements]);
  const [file, setFile] = useState<File | null>(null);
  const [placementId, setPlacementId] = useState<string | null>(null);
  const [heldAt, setHeldAt] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = progress !== null;

  return (
    <DialogShell
      title="Upload a recording"
      description="The recording is stored and queued for transcription."
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Upload"
      busyLabel="Uploading…"
      canSubmit={file !== null && placementId !== null && heldAt !== ""}
      onSubmit={async () => {
        if (!file || !placementId || !heldAt) return;
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
          setError(`The file is larger than ${MAX_UPLOAD_MB} MB`);
          return;
        }
        setError(null);
        setProgress(0);
        try {
          await uploadSession({
            file,
            placementId,
            heldAt: ukLocalToIso(heldAt),
            onProgress: (p) => setProgress(p.percentage),
          });
          toast.success("Uploaded and queued for transcription");
          onCreated();
          onClose();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Upload failed");
          setProgress(null);
        }
      }}
    >
      <FileDropZone
        selectedFile={file}
        accept={RECORDING_ACCEPT}
        hint={`MP4, MOV, WebM, MP3, WAV, M4A, OGG (at most ${MAX_UPLOAD_MB} MB)`}
        onFileSelect={(selected) => {
          setFile(selected);
          const fromName = heldAtFromFilename(selected.name);
          if (fromName) setHeldAt(fromName);
        }}
      />
      <FilteredSelect
        label="Placement"
        options={options}
        value={placementId}
        onChange={setPlacementId}
        searchPlaceholder="Search by consultant, client or project"
      />
      <HeldAtField value={heldAt} onChange={setHeldAt} />
      {progress !== null && (
        <UploadProgress percentage={progress} isComplete={progress === 100} />
      )}
    </DialogShell>
  );
}

export function UrlSessionDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { items: placements } = usePlacements(true);
  const options = useMemo(() => placementChoices(placements), [placements]);
  const [url, setUrl] = useState("");
  const [placementId, setPlacementId] = useState<string | null>(null);
  const [heldAt, setHeldAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <DialogShell
      title="Add a recording from a URL"
      description="The address is checked now; the recording is downloaded and transcribed in the background. Only public https addresses work."
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Add"
      busyLabel="Checking…"
      canSubmit={
        url.trim().startsWith("https://") &&
        placementId !== null &&
        heldAt !== ""
      }
      onSubmit={async () => {
        if (!placementId || !heldAt) return;
        setBusy(true);
        setError(null);
        try {
          await sessionFromUrl(url.trim(), placementId, ukLocalToIso(heldAt));
          toast.success("Queued for download and transcription");
          onCreated();
          onClose();
        } catch (err) {
          setError(saveErrorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="recording-url">Recording URL</Label>
        <Input
          id="recording-url"
          type="url"
          placeholder="https://"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            const fromName = heldAtFromFilename(urlFilename(e.target.value));
            if (fromName && !heldAt) setHeldAt(fromName);
          }}
        />
      </div>
      <FilteredSelect
        label="Placement"
        options={options}
        value={placementId}
        onChange={setPlacementId}
        searchPlaceholder="Search by consultant, client or project"
      />
      <HeldAtField value={heldAt} onChange={setHeldAt} />
    </DialogShell>
  );
}
