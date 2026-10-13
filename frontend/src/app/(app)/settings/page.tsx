import { Settings } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
          Settings
        </h2>
        <p className="text-sm text-muted-foreground">
          Your preferences for the app.
        </p>
      </div>
      <EmptyState
        icon={<Settings />}
        title="Settings coming soon"
        description="Application settings and preferences will be available in a future update."
      />
    </div>
  );
}
