import { RiskBoard } from "@/components/health/RiskBoard";

export default function RiskBoardPage() {
  return (
    <div className="space-y-2">
      <h2 className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
        Risk board
      </h2>
      <RiskBoard />
    </div>
  );
}
