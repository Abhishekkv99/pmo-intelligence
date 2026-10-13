import { SquareCheck } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";

export default function ActionsPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
          Actions
        </h2>
        <p className="text-sm text-muted-foreground">
          What was agreed on calls, by owner and due date.
        </p>
      </div>
      <EmptyState
        icon={<SquareCheck />}
        title="No open actions"
        description="Actions agreed on calls and in the group chats will appear here by owner and due date."
      />
    </div>
  );
}
