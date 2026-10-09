import { describe, it, expect, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => ({ user: null, isLoading: false, logout: vi.fn() }),
}));

import { visibleNavItems } from "./Sidebar";

describe("visibleNavItems", () => {
  it("shows every link, Admin included, to a global role", () => {
    const labels = visibleNavItems(true).map((item) => item.label);
    expect(labels).toEqual([
      "Risk board",
      "Sessions",
      "Actions",
      "Admin",
      "Settings",
    ]);
  });

  it("hides Admin from everyone else, leaving the other links", () => {
    const labels = visibleNavItems(false).map((item) => item.label);
    expect(labels).toEqual(["Risk board", "Sessions", "Actions", "Settings"]);
  });

  it("points the risk board at the home route", () => {
    const riskBoard = visibleNavItems(false).find(
      (item) => item.label === "Risk board",
    );
    expect(riskBoard?.href).toBe("/");
  });
});
