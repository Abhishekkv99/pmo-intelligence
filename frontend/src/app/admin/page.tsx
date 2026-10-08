import { Suspense } from "react";
import { AdminView } from "@/components/admin/AdminView";
import { MainLayout } from "@/components/layout/MainLayout";

export default function AdminPage() {
  return (
    <MainLayout>
      {/* AdminView reads the tab from the URL; useSearchParams needs a Suspense boundary */}
      <Suspense>
        <AdminView />
      </Suspense>
    </MainLayout>
  );
}
