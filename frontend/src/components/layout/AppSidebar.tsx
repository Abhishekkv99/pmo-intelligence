"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsUpDown, LogOut } from "lucide-react";
import { APP_NAME, ROUTES } from "@/lib/constants";
import { useAuth } from "@/components/providers/AuthProvider";
import { hasGlobalRole, roleLabel } from "@/lib/roles";
import { LogoMark } from "@/components/brand/Logo";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { getActiveHref, visibleNavItems } from "./nav";

/** "Alex Vaughan" → "AV"; one name gives one letter. */
export function initials(fullName: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0].charAt(0);
  const last = words.length > 1 ? words[words.length - 1].charAt(0) : "";
  return (first + last).toUpperCase();
}

// The active item is the lavender-tinted pill of the Twilight shell.
const ITEM_CLASSES =
  "text-sidebar-foreground/75 data-[active=true]:bg-sidebar-primary data-[active=true]:text-lavender data-[active=true]:inset-ring data-[active=true]:inset-ring-lavender/25";

export function AppSidebar() {
  const pathname = usePathname();
  const activeHref = getActiveHref(pathname);
  const { user, logout } = useAuth();
  const { isMobile, setOpenMobile } = useSidebar();
  const items = visibleNavItems(hasGlobalRole(user?.role));

  // On a phone the sidebar is a drawer; following a link closes it.
  const closeDrawer = () => setOpenMobile(false);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            {/* A link, not a heading: page headings stay with the pages. */}
            {/* The menu button sizes its icons to 16px; the mark keeps 32px,
                which is also the icon rail's button, so the name is clipped there. */}
            <SidebarMenuButton size="lg" asChild className="[&>svg]:size-8">
              <Link href={ROUTES.home} onClick={closeDrawer}>
                <LogoMark className="size-8" decorative />
                <span className="text-[15px] font-bold tracking-tight">
                  {APP_NAME}
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[10px] tracking-wider uppercase">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={item.href === activeHref}
                    tooltip={item.label}
                    className={ITEM_CLASSES}
                  >
                    <Link href={item.href} onClick={closeDrawer}>
                      <item.icon aria-hidden />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {user && (
        <SidebarFooter className="border-t border-sidebar-border">
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    className="data-[state=open]:bg-sidebar-accent"
                  >
                    <Avatar className="size-8">
                      <AvatarFallback className="bg-lavender font-mono text-xs font-semibold text-twilight">
                        {initials(user.full_name)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="grid flex-1 text-left leading-tight">
                      <span className="truncate text-sm font-medium">
                        {user.full_name}
                      </span>
                      <span className="truncate text-xs text-sidebar-foreground/70">
                        {roleLabel(user.role)}
                      </span>
                    </span>
                    <ChevronsUpDown className="ml-auto" aria-hidden />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  side={isMobile ? "bottom" : "right"}
                  align="end"
                  className="w-56"
                >
                  <DropdownMenuLabel>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {user.full_name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {user.email}
                      </span>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout} className="cursor-pointer">
                    <LogOut aria-hidden />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      )}
      <SidebarRail />
    </Sidebar>
  );
}
