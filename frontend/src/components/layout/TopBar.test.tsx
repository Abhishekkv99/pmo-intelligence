import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SidebarProvider } from "@/components/ui/sidebar";

let mockPathname = "/";

vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }));
vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));

import { TopBar } from "./TopBar";

function renderTopBar() {
  return render(
    <SidebarProvider>
      <TopBar />
    </SidebarProvider>,
  );
}

describe("TopBar", () => {
  beforeEach(() => {
    mockPathname = "/";
  });

  it("names the current section, with no heading", () => {
    renderTopBar();
    const current = screen.getByText("Risk board");
    expect(current).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("links back to the risk board from a placement", () => {
    mockPathname = "/placements/abc";
    renderTopBar();
    expect(screen.getByRole("link", { name: "Risk board" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByText("Placement")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("links back to the sessions list from a session", () => {
    mockPathname = "/sessions/abc";
    renderTopBar();
    expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute(
      "href",
      "/sessions",
    );
    expect(screen.getByText("Session")).toHaveAttribute("aria-current", "page");
  });

  it("has the sidebar toggle and the theme menu", () => {
    renderTopBar();
    expect(
      screen.getByRole("button", { name: "Toggle Sidebar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /toggle theme/i }),
    ).toBeInTheDocument();
  });
});
