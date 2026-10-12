import { PlacementHealthView } from "@/components/health/PlacementHealthView";

export default async function PlacementPage({
  params,
}: {
  params: Promise<{ placementId: string }>;
}) {
  const { placementId } = await params;
  return <PlacementHealthView placementId={placementId} />;
}
