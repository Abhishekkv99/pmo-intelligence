"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Pencil, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { DataTable } from "@/components/common/DataTable";
import { saveErrorMessage } from "@/components/admin/register/fields";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { requestTeamsScan, useTeamsChats } from "@/hooks/useTeamsChats";
import { formatUkDateTime } from "@/lib/recordings";
import {
  chatsNeedingPerson,
  HISTORY_LABELS,
  MATCH_LABELS,
  needsPerson,
  TEAMS_CHAT_MATCHES,
  TEAMS_WATCH_STATES,
  WATCH_LABELS,
} from "@/lib/teams";
import type { TeamsChat, TeamsChatList } from "@/types/teams";
import {
  ChooseMemberDialog,
  ChoosePlacementDialog,
  CreatePlacementDialog,
} from "./dialogs";

const ALL = "all";

type Dialog =
  | { kind: "placement"; chat: TeamsChat }
  | { kind: "create"; chat: TeamsChat }
  | { kind: "member"; chat: TeamsChat };

function ScanSummaryLine({ list }: { list: TeamsChatList }) {
  const schedule = list.discovery_enabled
    ? "Discovery runs daily."
    : "Discovery is off on this environment.";
  const watching = list.watching_enabled
    ? ""
    : " Watching is off: no member list is read yet.";
  const scan = list.latest_scan;
  if (!scan) {
    return (
      <p className="text-sm text-muted-foreground">
        No discovery yet. {schedule}
        {watching}
      </p>
    );
  }
  const when = formatUkDateTime(scan.finished_at ?? scan.started_at);
  if (scan.status === "failed") {
    return (
      <p className="text-sm text-destructive">
        Last discovery failed at {when}:{" "}
        {scan.error_message ?? "no reason given"}. {schedule}
        {watching}
      </p>
    );
  }
  if (scan.status === "running") {
    return (
      <p className="text-sm text-muted-foreground">
        Discovery is running (started {when}). {schedule}
        {watching}
      </p>
    );
  }
  return (
    <p className="text-sm text-muted-foreground">
      Last discovery {when}: {scan.chats_seen} chats ({scan.chats_added} new,{" "}
      {scan.chats_matched} matched). {schedule}
      {watching}
    </p>
  );
}

function Problem({ chat }: { chat: TeamsChat }) {
  if (needsPerson(chat) === "consultant") {
    return (
      <span>
        {chat.consultant_member_match === "needs_choice"
          ? "Several members could be the consultant"
          : "No member matches the consultant"}
        {chat.placement ? ` (${chat.placement.consultant_name})` : ""}
      </span>
    );
  }
  if (chat.match_status === "needs_choice") {
    return (
      <span>
        Could be{" "}
        {chat.candidates
          .map((c) => `${c.consultant_name} at ${c.client_name}`)
          .join(" or ")}
      </span>
    );
  }
  if (chat.match_status === "unparsed") {
    return <span>{chat.error_message ?? MATCH_LABELS.unparsed}</span>;
  }
  return <span>No placement in the register matches the title</span>;
}

function NeedsPersonCard({
  chats,
  onOpen,
}: {
  chats: TeamsChat[];
  onOpen: (dialog: Dialog) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Chats waiting for a person ({chats.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {chats.map((chat) => (
          <div
            key={chat.id}
            data-testid="waiting-chat"
            className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0 last:pb-0"
          >
            <div className="min-w-0">
              <div className="font-mono text-xs break-all">{chat.title}</div>
              <div className="text-xs text-muted-foreground">
                <Problem chat={chat} />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {needsPerson(chat) === "consultant" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onOpen({ kind: "member", chat })}
                >
                  Choose consultant
                </Button>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onOpen({ kind: "placement", chat })}
                  >
                    {chat.match_status === "needs_choice"
                      ? "Choose placement"
                      : "Link placement"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onOpen({ kind: "create", chat })}
                  >
                    Create from title
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function FilterSelect({
  label,
  all,
  value,
  onChange,
  options,
}: {
  label: string;
  all: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-auto" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{all}</SelectItem>
        {options.map(([id, name]) => (
          <SelectItem key={id} value={id}>
            {name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * Admin > Teams: the PMO group chats (titled "PRJ ITC …"). Chats waiting for a
 * person sit in a card at the top, each with its fix; below, every chat with
 * its placement, match, watch state, consultant member, last message and
 * history, filtered by match and watch state.
 */
export function TeamsTab({ enabled }: { enabled: boolean }) {
  const { list, isLoading, error, mutate } = useTeamsChats(enabled);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [scanning, setScanning] = useState(false);
  const [match, setMatch] = useState<string>(ALL);
  const [watch, setWatch] = useState<string>(ALL);

  const chats = useMemo(() => list?.chats ?? [], [list]);
  const waiting = useMemo(() => chatsNeedingPerson(chats), [chats]);
  const shown = useMemo(
    () =>
      chats.filter(
        (c) =>
          (match === ALL || c.match_status === match) &&
          (watch === ALL || c.watch_state === watch),
      ),
    [chats, match, watch],
  );

  const columns = useMemo<ColumnDef<TeamsChat>[]>(
    () => [
      {
        id: "title",
        header: "Chat",
        accessorFn: (c) => c.title,
        cell: ({ row }) => (
          <div className="max-w-xs font-mono text-xs break-all">
            {row.original.title}
          </div>
        ),
      },
      {
        id: "placement",
        header: "Placement",
        accessorFn: (c) =>
          c.placement
            ? `${c.placement.consultant_name} ${c.placement.client_name} ${c.placement.project_name}`
            : "",
        cell: ({ row }) => {
          const chat = row.original;
          return (
            <div className="flex items-start gap-1">
              {chat.placement ? (
                <div>
                  <div className="font-medium">
                    {chat.placement.consultant_name}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {chat.placement.client_name} · {chat.placement.project_name}
                  </div>
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">None</span>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label={`Change the placement of ${chat.title}`}
                onClick={() => setDialog({ kind: "placement", chat })}
              >
                <Pencil className="size-3.5" />
              </Button>
            </div>
          );
        },
      },
      {
        id: "match",
        header: "Match",
        accessorFn: (c) => MATCH_LABELS[c.match_status],
      },
      {
        id: "watch",
        header: "Watch",
        accessorFn: (c) => WATCH_LABELS[c.watch_state],
        cell: ({ row }) => {
          const chat = row.original;
          return (
            <div>
              <div>{WATCH_LABELS[chat.watch_state]}</div>
              {chat.watch_state === "failed" && chat.error_message && (
                <div className="text-xs text-destructive">
                  {chat.error_message}
                </div>
              )}
              {chat.watch_state === "watching" && chat.watched_at && (
                <div className="text-xs text-muted-foreground">
                  since {formatUkDateTime(chat.watched_at)}
                </div>
              )}
            </div>
          );
        },
      },
      {
        id: "member",
        header: "Consultant in the chat",
        accessorFn: (c) => c.consultant_member?.name ?? "",
        cell: ({ row }) => {
          const chat = row.original;
          if (chat.consultant_member) return chat.consultant_member.name;
          if (chat.members.length === 0) {
            return <span className="text-muted-foreground">Not read</span>;
          }
          return (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDialog({ kind: "member", chat })}
            >
              Choose
            </Button>
          );
        },
      },
      {
        id: "last",
        header: "Last message",
        accessorFn: (c) => c.last_message_at ?? "",
        cell: ({ row }) =>
          row.original.last_message_at ? (
            formatUkDateTime(row.original.last_message_at)
          ) : (
            <span className="text-muted-foreground">None</span>
          ),
      },
      {
        id: "history",
        header: "History",
        accessorFn: (c) => HISTORY_LABELS[c.history_state],
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
        <Button
          variant="outline"
          disabled={scanning || list?.discovery_enabled === false}
          title={
            list?.discovery_enabled === false
              ? "Discovery is off on this environment"
              : undefined
          }
          onClick={async () => {
            setScanning(true);
            try {
              const { queued } = await requestTeamsScan();
              toast.success(
                queued
                  ? "Discovery queued; new chats appear in a minute or two"
                  : "Discovery is already waiting to start",
              );
              void mutate();
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
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {waiting.length > 0 && (
        <NeedsPersonCard chats={waiting} onOpen={setDialog} />
      )}

      <div className="flex flex-wrap gap-2">
        <FilterSelect
          label="Match filter"
          all="Every match"
          value={match}
          onChange={setMatch}
          options={TEAMS_CHAT_MATCHES.map((m) => [m, MATCH_LABELS[m]])}
        />
        <FilterSelect
          label="Watch filter"
          all="Every watch state"
          value={watch}
          onChange={setWatch}
          options={TEAMS_WATCH_STATES.map((w) => [w, WATCH_LABELS[w]])}
        />
      </div>

      <DataTable
        columns={columns}
        data={shown}
        searchPlaceholder="Search chat, consultant, client"
        emptyMessage="No PRJ ITC chats yet. Discovery lists them from the PMO accounts' chats."
        isLoading={isLoading}
      />

      {dialog?.kind === "placement" && (
        <ChoosePlacementDialog
          chat={dialog.chat}
          onClose={() => setDialog(null)}
          onSaved={() => void mutate()}
        />
      )}
      {dialog?.kind === "create" && (
        <CreatePlacementDialog
          chat={dialog.chat}
          onClose={() => setDialog(null)}
          onSaved={() => void mutate()}
        />
      )}
      {dialog?.kind === "member" && (
        <ChooseMemberDialog
          chat={dialog.chat}
          onClose={() => setDialog(null)}
          onSaved={() => void mutate()}
        />
      )}
    </div>
  );
}
