import { Suspense } from "react";
import { AdminView } from "@/components/admin/AdminView";

export default function AdminPage() {
  // AdminView reads the tab from the URL; useSearchParams needs a Suspense boundary
  return (
    <Suspense>
      <AdminView />
    </Suspense>
  );
}
