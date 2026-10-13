"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { ShieldCheck } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { hasGlobalRole } from "@/lib/roles";
import { RecordingsTab } from "./recordings/RecordingsTab";
import { RegisterTab } from "./register/RegisterTab";
import { UsersTab } from "./users/UsersTab";
import { ProcessingStatusPanel } from "./ProcessingStatusPanel";

export const ADMIN_TABS = [
  { value: "register", label: "Register" },
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
      <div className="space-y-2">
        <h2 className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
          Admin
        </h2>
        {isGlobal && (
          <p className="text-sm text-muted-foreground">
            The placement register, who can sign in, the recordings folder and
            the processing queue.
          </p>
        )}
      </div>
      {isGlobal ? (
        <Tabs value={tab} onValueChange={selectTab} className="space-y-4">
          <TabsList
            variant="line"
            className="h-10 w-full justify-start gap-4 border-b p-0"
          >
            {ADMIN_TABS.map((t) => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="flex-none px-1 data-[state=active]:after:bg-primary"
              >
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="register">
            <RegisterTab />
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
          icon={<ShieldCheck />}
          title="Admin is available to PMO managers and admins"
          description="Ask a PMO manager if you need access."
        />
      )}
    </div>
  );
}
