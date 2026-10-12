import { EmptyState } from "@/components/common/EmptyState";

export default function ActionsPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold tracking-tight">Actions</h2>
      <EmptyState
        title="No open actions"
        description="Actions agreed on calls and in the group chats will appear here by owner and due date."
      />
    </div>
  );
}
