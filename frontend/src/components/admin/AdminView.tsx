"use client";

import { useAuth } from "@/components/providers/AuthProvider";
import { EmptyState } from "@/components/common/EmptyState";
import { hasGlobalRole } from "@/lib/roles";
import { ProcessingStatusPanel } from "./ProcessingStatusPanel";

export function AdminView() {
  const { user } = useAuth();
  const isGlobal = hasGlobalRole(user?.role);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold tracking-tight">Admin</h2>
      {isGlobal ? (
        <ProcessingStatusPanel enabled />
      ) : (
        <EmptyState
          title="Admin is available to PMO managers and admins"
          description="Ask a PMO manager if you need access."
        />
      )}
    </div>
  );
}
