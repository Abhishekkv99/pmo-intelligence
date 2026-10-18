"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { saveErrorMessage } from "@/components/admin/register/fields";
import { DialogShell } from "@/components/admin/recordings/dialogs";
import {
  FilteredSelect,
  type FilteredOption,
} from "@/components/admin/recordings/FilteredSelect";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  chooseChatPlacement,
  chooseConsultantMember,
  createChatPlacement,
} from "@/hooks/useTeamsChats";
import { usePlacements } from "@/hooks/useRegister";
import { placementLabel } from "@/lib/teams";
import type { TeamsChat } from "@/types/teams";

interface ChatDialogProps {
  chat: TeamsChat;
  onClose: () => void;
  onSaved: () => void;
}

function TitleLine({ chat }: { chat: TeamsChat }) {
  return <span className="font-mono text-xs break-all">{chat.title}</span>;
}

// --- Linking a chat to a placement --------------------------------------------

export function ChoosePlacementDialog({
  chat,
  onClose,
  onSaved,
}: ChatDialogProps) {
  const { items: placements } = usePlacements(true);
  const [placementId, setPlacementId] = useState<string | null>(
    chat.placement?.id ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The placements the title could mean first, then every other placement.
  const options = useMemo<FilteredOption[]>(() => {
    const candidateIds = new Set(chat.candidates.map((c) => c.id));
    const first = chat.candidates.map((c) => ({
      value: c.id,
      label: `${placementLabel(c)} (matches the title)`,
    }));
    const rest = placements
      .filter((p) => !candidateIds.has(p.id))
      .map((p) => ({
        value: p.id,
        label: placementLabel({
          consultant_name: p.consultant.full_name,
          client_name: p.client.name,
          project_name: p.project.name,
          start_date: p.start_date,
          expected_end_date: p.expected_end_date,
        }),
      }));
    return [...first, ...rest];
  }, [chat.candidates, placements]);

  return (
    <DialogShell
      title="Link the chat to a placement"
      description={
        <>
          <TitleLine chat={chat} />
          <p className="mt-2">
            Discovery keeps this choice. The chat is watched while the placement
            is active.
          </p>
        </>
      }
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Link"
      busyLabel="Linking…"
      canSubmit={placementId !== null}
      onSubmit={async () => {
        if (!placementId) return;
        setBusy(true);
        setError(null);
        try {
          await chooseChatPlacement(chat.id, placementId);
          toast.success("Chat linked to the placement");
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
        label="Placement"
        options={options}
        value={placementId}
        onChange={setPlacementId}
        searchPlaceholder="Filter by consultant, client or project"
      />
    </DialogShell>
  );
}

// --- Creating the placement from the title ------------------------------------

export function CreatePlacementDialog({
  chat,
  onClose,
  onSaved,
}: ChatDialogProps) {
  const [line, setLine] = useState(chat.quick_add_line);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <DialogShell
      title="Create the placement from the title"
      description={
        <>
          <TitleLine chat={chat} />
          <p className="mt-2">
            The line is written as the quick add writes it: the client and
            consultant are found or created, and the placement goes under the
            client&apos;s project &ldquo;To be confirmed&rdquo; unless it
            exists. Edit the line if the title is wrong.
          </p>
        </>
      }
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Create and link"
      busyLabel="Creating…"
      canSubmit={line.trim().length > 0}
      onSubmit={async () => {
        setBusy(true);
        setError(null);
        try {
          const result = await createChatPlacement(chat.id, line.trim());
          if (result.applied) {
            toast.success("Placement written and chat linked");
            onSaved();
            onClose();
          } else {
            setError(
              result.lines.flatMap((l) => l.errors).join("; ") ||
                "The line was not written",
            );
          }
        } catch (err) {
          setError(saveErrorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="teams-quick-add-line">Quick add line</Label>
        <Textarea
          id="teams-quick-add-line"
          className="font-mono text-sm"
          rows={3}
          value={line}
          onChange={(e) => setLine(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          PRJ ITC &lt;stack&gt; - &lt;consultant&gt; - &lt;client&gt; - D/M/YYYY
          - D/M/YYYY
        </p>
      </div>
    </DialogShell>
  );
}

// --- Choosing the consultant among the members ---------------------------------

export function ChooseMemberDialog({
  chat,
  onClose,
  onSaved,
}: ChatDialogProps) {
  const [oid, setOid] = useState<string | null>(
    chat.consultant_member?.oid ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = useMemo<FilteredOption[]>(
    () => chat.members.map((m) => ({ value: m.oid, label: m.name || m.oid })),
    [chat.members],
  );

  return (
    <DialogShell
      title="Which member is the consultant?"
      description={
        <>
          <TitleLine chat={chat} />
          <p className="mt-2">
            {chat.placement
              ? `The placement's consultant is ${chat.placement.consultant_name}.`
              : "The chat has no placement yet."}{" "}
            Their posts are counted as the consultant&apos;s.
          </p>
        </>
      }
      onClose={onClose}
      error={error}
      busy={busy}
      submitLabel="Save"
      busyLabel="Saving…"
      canSubmit={oid !== null}
      onSubmit={async () => {
        if (!oid) return;
        setBusy(true);
        setError(null);
        try {
          await chooseConsultantMember(chat.id, oid);
          toast.success("Consultant member saved");
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
        label="Member"
        options={options}
        value={oid}
        onChange={setOid}
        searchPlaceholder="Filter by name"
      />
    </DialogShell>
  );
}
