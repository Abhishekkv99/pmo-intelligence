"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ROUTES, APP_NAME } from "@/lib/constants";
import { useAuth } from "@/components/providers/AuthProvider";
import { hasGlobalRole } from "@/lib/roles";

interface NavItem {
  label: string;
  href: string;
  /** Shown only to a global role (`pmo_manager`, `admin`); the page's routes answer 403 otherwise. */
  globalOnly?: boolean;
}

const navItems: NavItem[] = [
  { label: "Risk board", href: ROUTES.home },
  { label: "Sessions", href: ROUTES.sessions },
  { label: "Actions", href: ROUTES.actions },
  { label: "Admin", href: ROUTES.admin, globalOnly: true },
  { label: "Settings", href: ROUTES.settings },
];

function getActiveHref(pathname: string): string | null {
  const matches = navItems.filter(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
  );
  if (matches.length === 0) return null;
  // Most specific match = longest href
  return matches.reduce((a, b) => (a.href.length >= b.href.length ? a : b))
    .href;
}

export function visibleNavItems(isGlobal: boolean): NavItem[] {
  return navItems.filter((item) => !item.globalOnly || isGlobal);
}

export function Sidebar() {
  const pathname = usePathname();
  const activeHref = getActiveHref(pathname);
  const { user } = useAuth();
  const items = visibleNavItems(hasGlobalRole(user?.role));

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-border bg-sidebar">
      <div className="flex h-16 items-center border-b border-sidebar-border px-6">
        <Link href={ROUTES.home} className="text-lg font-semibold">
          {APP_NAME}
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-4">
        {items.map((item) => {
          const isActive = item.href === activeHref;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-sidebar-primary text-sidebar-primary-foreground font-semibold"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
