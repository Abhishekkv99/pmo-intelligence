import { MainLayout } from "@/components/layout/MainLayout";
import { RiskBoard } from "@/components/health/RiskBoard";

export default function RiskBoardPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold tracking-tight">Risk board</h2>
        <RiskBoard />
      </div>
    </MainLayout>
  );
}
