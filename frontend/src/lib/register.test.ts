import { describe, it, expect } from "vitest";
import { humanize } from "./register";
import { NONE, orNull } from "@/components/admin/register/fields";
import { parseSkills } from "@/components/admin/register/ConsultantsTable";

describe("register helpers", () => {
  it("humanizes enumeration values", () => {
    expect(humanize("not_due")).toBe("Not due");
    expect(humanize("pmo_manager")).toBe("Pmo manager");
  });

  it("turns empty and none into null for the API", () => {
    expect(orNull("")).toBeNull();
    expect(orNull("   ")).toBeNull();
    expect(orNull(NONE)).toBeNull();
    expect(orNull(" B ")).toBe("B");
  });

  it("splits skills on commas and drops blanks", () => {
    expect(parseSkills("Python, AWS ,, SQL ")).toEqual([
      "Python",
      "AWS",
      "SQL",
    ]);
    expect(parseSkills("")).toEqual([]);
  });
});
