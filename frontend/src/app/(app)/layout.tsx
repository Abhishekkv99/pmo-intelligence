import { cookies } from "next/headers";
import { MainLayout } from "@/components/layout/MainLayout";

// The shell for every signed-in page. One layout, so the sidebar stays mounted
// as the user moves between pages; the route group leaves the URLs unchanged.
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  // Open unless the user collapsed it (the sidebar writes `sidebar_state`).
  const defaultOpen = cookieStore.get("sidebar_state")?.value !== "false";
  return <MainLayout defaultOpen={defaultOpen}>{children}</MainLayout>;
}
