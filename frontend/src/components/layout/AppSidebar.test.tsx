import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Role } from "@/lib/roles";
import { SidebarProvider } from "@/components/ui/sidebar";

let mockPathname = "/";
const mockLogout = vi.fn();
let mockUser: {
  full_name: string;
  email: string;
  role: Role | null;
} | null = null;

vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }));
vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => ({ user: mockUser, isLoading: false, logout: mockLogout }),
}));

import { AppSidebar, initials } from "./AppSidebar";

function renderSidebar() {
  return render(
    <SidebarProvider>
      <AppSidebar />
    </SidebarProvider>,
  );
}

function navLink(name: string) {
  const nav = screen
    .getByText("Navigation")
    .closest("[data-slot='sidebar-group']");
  return within(nav as HTMLElement).getByRole("link", { name });
}

describe("AppSidebar", () => {
  beforeEach(() => {
    mockPathname = "/";
    mockLogout.mockClear();
    mockUser = {
      full_name: "Alex Vaughan",
      email: "alex@example.com",
      role: "pmo_manager",
    };
    // Radix menus use pointer capture and scrolling that jsdom lacks.
    Element.prototype.hasPointerCapture = vi.fn(() => false);
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("links the logo to the risk board without making it a heading", () => {
    renderSidebar();
    expect(
      screen.getByRole("link", { name: "PMO Intelligence" }),
    ).toHaveAttribute("href", "/");
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("marks the current page's item active and no other", () => {
    mockPathname = "/sessions";
    renderSidebar();
    expect(navLink("Sessions")).toHaveAttribute("data-active", "true");
    expect(navLink("Risk board")).toHaveAttribute("data-active", "false");
  });

  it("keeps the risk board active on a placement page", () => {
    mockPathname = "/placements/abc";
    renderSidebar();
    expect(navLink("Risk board")).toHaveAttribute("data-active", "true");
  });

  it("shows Admin to a global role", () => {
    renderSidebar();
    expect(navLink("Admin")).toHaveAttribute("href", "/admin");
  });

  it("hides Admin from other roles", () => {
    mockUser = { ...mockUser!, role: "ps" };
    renderSidebar();
    const nav = screen
      .getByText("Navigation")
      .closest("[data-slot='sidebar-group']") as HTMLElement;
    expect(
      within(nav).queryByRole("link", { name: "Admin" }),
    ).not.toBeInTheDocument();
    expect(within(nav).getAllByRole("link")).toHaveLength(4);
  });

  it("shows the user's initials, name and role in the footer", () => {
    renderSidebar();
    expect(screen.getByText("AV")).toBeInTheDocument();
    expect(screen.getByText("Alex Vaughan")).toBeInTheDocument();
    expect(screen.getByText("PMO manager")).toBeInTheDocument();
  });

  it("signs out from the user menu", async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.click(screen.getByRole("button", { name: /Alex Vaughan/ }));
    expect(await screen.findByText("alex@example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it("has no user menu while signed out", () => {
    mockUser = null;
    renderSidebar();
    expect(screen.queryByText("PMO manager")).not.toBeInTheDocument();
    expect(navLink("Risk board")).toBeInTheDocument();
  });
});

describe("initials", () => {
  it.each([
    ["Alex Vaughan", "AV"],
    ["Mei Ling Chen", "MC"],
    ["  priya  ", "P"],
    ["", "?"],
  ])("gives %j as %j", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});
