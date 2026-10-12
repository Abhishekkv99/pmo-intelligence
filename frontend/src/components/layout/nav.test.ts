import { describe, it, expect } from "vitest";
import { getActiveHref, getBreadcrumb, visibleNavItems } from "./nav";

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

  it("gives every item an icon", () => {
    for (const item of visibleNavItems(true)) {
      expect(item.icon).toBeDefined();
    }
  });
});

describe("getActiveHref", () => {
  it.each([
    ["/", "/"],
    ["/placements/abc", "/"],
    ["/sessions", "/sessions"],
    ["/sessions/abc", "/sessions"],
    ["/actions", "/actions"],
    ["/admin", "/admin"],
    ["/settings", "/settings"],
  ])("marks %s as under %s", (pathname, href) => {
    expect(getActiveHref(pathname)).toBe(href);
  });

  it("marks nothing for a path off the nav", () => {
    expect(getActiveHref("/login")).toBeNull();
  });

  it("does not take a path that only shares a prefix", () => {
    expect(getActiveHref("/sessionsx")).toBeNull();
  });
});

describe("getBreadcrumb", () => {
  it("names the section on a section page", () => {
    expect(getBreadcrumb("/")).toEqual([{ label: "Risk board" }]);
    expect(getBreadcrumb("/admin")).toEqual([{ label: "Admin" }]);
  });

  it("puts a placement under the risk board, the board a link", () => {
    expect(getBreadcrumb("/placements/abc")).toEqual([
      { label: "Risk board", href: "/" },
      { label: "Placement" },
    ]);
  });

  it("puts a session under the sessions list, the list a link", () => {
    expect(getBreadcrumb("/sessions/abc")).toEqual([
      { label: "Sessions", href: "/sessions" },
      { label: "Session" },
    ]);
  });

  it("is empty off the nav", () => {
    expect(getBreadcrumb("/login")).toEqual([]);
  });
});
