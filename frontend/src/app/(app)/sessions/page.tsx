import { SessionsList } from "@/components/sessions/SessionsList";

export default function SessionsPage() {
  return (
    <div className="space-y-2">
      <h2 className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
        Sessions
      </h2>
      <p className="text-sm text-muted-foreground">
        Every recorded call you can see, newest first.
      </p>
      <div className="pt-2">
        <SessionsList />
      </div>
    </div>
  );
}
