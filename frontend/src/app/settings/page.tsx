import { MainLayout } from "@/components/layout/MainLayout";
import { EmptyState } from "@/components/common/EmptyState";

export default function SettingsPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
        <EmptyState
          title="Settings coming soon"
          description="Application settings and preferences will be available in a future update."
        />
      </div>
    </MainLayout>
  );
}
