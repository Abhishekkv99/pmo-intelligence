import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

/**
 * The signed-in shell: the collapsible sidebar (a drawer on a phone) and the
 * top bar around the page. `defaultOpen` comes from the `sidebar_state`
 * cookie, so the sidebar renders open or collapsed on the server as it was
 * left. `<main>` (SidebarInset) is the scroll container.
 */
export function MainLayout({
  children,
  defaultOpen = true,
}: {
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <SidebarProvider defaultOpen={defaultOpen} className="h-svh">
      <AppSidebar />
      <SidebarInset className="overflow-y-auto">
        <TopBar />
        <div className="flex-1 p-4 md:p-6">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
