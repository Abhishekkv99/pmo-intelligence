import { MainLayout } from "@/components/layout/MainLayout";
import { EmptyState } from "@/components/common/EmptyState";

export default function RiskBoardPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold tracking-tight">Risk board</h2>
        <EmptyState
          title="No placements yet"
          description="Every active placement will appear here with its health score, trend and open risk flags."
        />
      </div>
    </MainLayout>
  );
}
