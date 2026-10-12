import { SessionsList } from "@/components/sessions/SessionsList";

export default function SessionsPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold tracking-tight">Sessions</h2>
      <SessionsList />
    </div>
  );
}
