"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { EmptyState } from "@/components/common/EmptyState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { hasGlobalRole } from "@/lib/roles";
import { RecordingsTab } from "./recordings/RecordingsTab";
import { ImportTab } from "./register/ImportTab";
import { RegisterTab } from "./register/RegisterTab";
import { UsersTab } from "./users/UsersTab";
import { ProcessingStatusPanel } from "./ProcessingStatusPanel";

export const ADMIN_TABS = [
  { value: "register", label: "Register" },
  { value: "import", label: "Import" },
  { value: "users", label: "Users and roles" },
  { value: "recordings", label: "Recordings" },
  { value: "processing", label: "Processing" },
] as const;

type AdminTab = (typeof ADMIN_TABS)[number]["value"];

function isAdminTab(value: string | null): value is AdminTab {
  return ADMIN_TABS.some((tab) => tab.value === value);
}

export function AdminView() {
  const { user } = useAuth();
  const isGlobal = hasGlobalRole(user?.role);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const tab: AdminTab = isAdminTab(requested) ? requested : "register";

  // The tab lives in the URL (?tab=) so a link or a reload opens the same one.
  function selectTab(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", value);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold tracking-tight">Admin</h2>
      {isGlobal ? (
        <Tabs value={tab} onValueChange={selectTab} className="space-y-4">
          <TabsList>
            {ADMIN_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="register">
            <RegisterTab />
          </TabsContent>
          <TabsContent value="import">
            <ImportTab />
          </TabsContent>
          <TabsContent value="users">
            <UsersTab />
          </TabsContent>
          <TabsContent value="recordings">
            <RecordingsTab enabled={tab === "recordings"} />
          </TabsContent>
          <TabsContent value="processing">
            <ProcessingStatusPanel enabled={tab === "processing"} />
          </TabsContent>
        </Tabs>
      ) : (
        <EmptyState
          title="Admin is available to PMO managers and admins"
          description="Ask a PMO manager if you need access."
        />
      )}
    </div>
  );
}
