import { describe, it, expect } from "vitest";
import { GLOBAL_ROLES, ROLES, hasGlobalRole } from "./roles";

describe("roles", () => {
  it("lists the five backend roles", () => {
    expect(ROLES).toEqual(["pmo_manager", "sme", "tech_lead", "ps", "admin"]);
  });

  it("treats pmo_manager and admin as global", () => {
    expect(GLOBAL_ROLES).toEqual(["pmo_manager", "admin"]);
    expect(hasGlobalRole("pmo_manager")).toBe(true);
    expect(hasGlobalRole("admin")).toBe(true);
  });

  it("treats the scoped roles as not global", () => {
    expect(hasGlobalRole("sme")).toBe(false);
    expect(hasGlobalRole("tech_lead")).toBe(false);
    expect(hasGlobalRole("ps")).toBe(false);
  });

  it("treats a user with no role, or no user, as not global", () => {
    expect(hasGlobalRole(null)).toBe(false);
    expect(hasGlobalRole(undefined)).toBe(false);
  });
});
