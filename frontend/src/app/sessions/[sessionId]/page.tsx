import { MainLayout } from "@/components/layout/MainLayout";
import { SessionView } from "@/components/sessions/SessionView";

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return (
    <MainLayout>
      <SessionView sessionId={sessionId} />
    </MainLayout>
  );
}
