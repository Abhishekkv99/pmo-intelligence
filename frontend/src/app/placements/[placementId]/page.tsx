import { MainLayout } from "@/components/layout/MainLayout";
import { PlacementHealthView } from "@/components/health/PlacementHealthView";

export default async function PlacementPage({
  params,
}: {
  params: Promise<{ placementId: string }>;
}) {
  const { placementId } = await params;
  return (
    <MainLayout>
      <PlacementHealthView placementId={placementId} />
    </MainLayout>
  );
}
