import {
  Gauge,
  LayoutGrid,
  MessageSquare,
  Settings,
  SquareCheck,
  type LucideIcon,
} from "lucide-react";
import { ROUTES } from "@/lib/constants";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Shown only to a global role (`pmo_manager`, `admin`); the page's routes answer 403 otherwise. */
  globalOnly?: boolean;
  /** Other paths that belong to this item (a placement page is reached from the board). */
  alsoActiveOn?: string[];
  /** The breadcrumb's name for a page below this item (`/sessions/<id>` is a "Session"). */
  childLabel?: string;
}

const navItems: NavItem[] = [
  {
    label: "Risk board",
    href: ROUTES.home,
    icon: Gauge,
    alsoActiveOn: [ROUTES.placements],
  },
  {
    label: "Sessions",
    href: ROUTES.sessions,
    icon: MessageSquare,
    childLabel: "Session",
  },
  { label: "Actions", href: ROUTES.actions, icon: SquareCheck },
  { label: "Admin", href: ROUTES.admin, icon: LayoutGrid, globalOnly: true },
  { label: "Settings", href: ROUTES.settings, icon: Settings },
];

/** The placement page's breadcrumb name; it sits under the risk board. */
const PLACEMENT_LABEL = "Placement";

function isWithin(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

export function visibleNavItems(isGlobal: boolean): NavItem[] {
  return navItems.filter((item) => !item.globalOnly || isGlobal);
}

/** The nav item a path belongs to: the most specific match, or null. */
export function getActiveItem(pathname: string): NavItem | null {
  const matches = navItems.filter(
    (item) =>
      isWithin(pathname, item.href) ||
      (item.alsoActiveOn ?? []).some((path) => isWithin(pathname, path)),
  );
  if (matches.length === 0) return null;
  // Most specific match = longest href
  return matches.reduce((a, b) => (a.href.length >= b.href.length ? a : b));
}

export function getActiveHref(pathname: string): string | null {
  return getActiveItem(pathname)?.href ?? null;
}

export interface Crumb {
  label: string;
  /** Set on a parent crumb; the current page has none. */
  href?: string;
}

/**
 * The top bar's breadcrumb: the section, then the page below it when there is
 * one ("Risk board / Placement", "Sessions / Session"). Empty off the nav.
 */
export function getBreadcrumb(pathname: string): Crumb[] {
  const item = getActiveItem(pathname);
  if (!item) return [];
  if (pathname === item.href) return [{ label: item.label }];
  if (isWithin(pathname, ROUTES.placements)) {
    return [{ label: item.label, href: item.href }, { label: PLACEMENT_LABEL }];
  }
  if (item.childLabel) {
    return [{ label: item.label, href: item.href }, { label: item.childLabel }];
  }
  return [{ label: item.label }];
}
